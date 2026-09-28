"""Plays the golden dialogues through the real dialogue service and scores the answers.

    python -m app.eval_dialogues            # report
    python -m app.eval_dialogues --verbose  # plus every dialogue transcript

Runs in-process on an in-memory SQLite database, so it needs no server, no Ollama and
no network: the same numbers locally and in CI.
"""

from __future__ import annotations

import argparse
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
import app.models  # noqa: F401  (registers every table)
from app.repositories.conversations import ConversationRepository
from app.services.triage import TriageDialogueService
from helpflow_ai import KnowledgeBase, TriageEngine

GOLDEN = Path(__file__).resolve().parents[1] / "tests" / "golden" / "dialogues.yaml"
PROGRESS = {"TROUBLESHOOTING", "VERIFYING", "RESOLVED", "ESCALATED", "IN_PROGRESS"}
BUTTONS = {"@helped": "helped", "@not_helped": "not_helped", "@cannot": "cannot_perform"}
VAGUE_TITLE = "Проблема требует уточнения"
# A text fact holding a bare yes/no or a whole complaint is noise for the specialist.
_BARE = {"нет", "да", "не знаю", "неа", "ага"}
_COMPLAINT = re.compile(r"\bне (могу|работает|открывается|получается|пускает)\b")
TEXT_FACTS = {"service_name", "error_text", "since_when", "details"}


@dataclass
class Result:
    id: str
    tags: list[str]
    playbook: str
    status: str
    questions: int
    problems: list[str] = field(default_factory=list)
    transcript: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def _expected_end(status: str, answer_kind: str | None) -> str:
    if status == "RESOLVED":
        return "resolved"
    if status in {"ESCALATED", "IN_PROGRESS"}:
        return "escalated"
    if answer_kind == "document":
        return "answer"
    if status in {"TROUBLESHOOTING", "VERIFYING"}:
        return "step"
    return status.lower()


def play(service: TriageDialogueService, case: dict) -> Result:
    conversation = service.create_conversation()
    service.repository.session.commit()
    questions, progressed, asked = 0, False, []
    problems: list[str] = []
    transcript: list[str] = []
    for turn in case["say"]:
        conversation = service.get_conversation(conversation.id)
        before = len(conversation.messages)
        if turn in BUTTONS:
            if conversation.status != "TROUBLESHOOTING":
                problems.append(f"ждали шаг для «{turn}», а статус {conversation.status}")
                break
            conversation = service.record_step_result(conversation.id, BUTTONS[turn])
        else:
            if conversation.status not in {"NEW", "CLARIFYING", "VERIFYING"}:
                problems.append(f"реплика «{turn}» пришла в статусе {conversation.status}")
                break
            conversation = service.handle_message(conversation.id, turn)
        transcript.append(f"  → {turn}")
        new = [m for m in conversation.messages[before:] if m.role == "assistant"]
        transcript += [f"  ← {m.content}" for m in new]
        if conversation.status == "CLARIFYING" and new:
            text = new[-1].content
            if text in asked:
                problems.append(f"повторный вопрос: «{text}»")
            asked.append(text)
            if not progressed:
                questions += 1
        if conversation.status in PROGRESS or conversation.answer_kind == "document":
            progressed = True
        if conversation.status in {"ESCALATED", "IN_PROGRESS"} and any(
            m.content.rstrip().endswith("?") for m in new[:-1]
        ):
            problems.append("задал вопрос и в том же ходе передал специалисту")

    conversation = service.get_conversation(conversation.id)
    expected = case.get("playbook")
    allowed = expected if isinstance(expected, list) else [expected] if expected else []
    if allowed and conversation.playbook_id not in allowed:
        problems.append(f"сценарий {conversation.playbook_id}, ждали {' / '.join(allowed)}")
    limit = case.get("max_questions", 2)
    if questions > limit:
        problems.append(f"вопросов до первого действия: {questions} (можно {limit})")
    if case.get("end") and _expected_end(conversation.status, conversation.answer_kind) != case["end"]:
        problems.append(f"закончилось «{_expected_end(conversation.status, conversation.answer_kind)}», "
                        f"ждали «{case['end']}»")
    said = " ".join(m.content for m in conversation.messages if m.role == "assistant").lower()
    for phrase in case.get("forbid_text", []):
        if phrase.lower() in said:
            problems.append(f"помощник сказал лишнее: «{phrase}»")
    last_turn = transcript[transcript.index(f"  → {case['say'][-1]}"):] if transcript else []
    for phrase in case.get("expect_text", []):
        if not any(phrase.lower() in line.lower() for line in last_turn[1:]):
            problems.append(f"в ответ на последнюю реплику нет «{phrase}»")
    for fact, value in case.get("expect_fact", {}).items():
        if (conversation.known_facts or {}).get(fact) != value:
            problems.append(f"факт {fact} = «{(conversation.known_facts or {}).get(fact)}», ждали «{value}»")
    if case.get("forbid_end") and _expected_end(conversation.status, conversation.answer_kind) == case["forbid_end"]:
        problems.append(f"закончилось «{case['forbid_end']}», а не должно")
    for fact, value in (conversation.known_facts or {}).items():
        text = str(value).strip().lower()
        if fact in TEXT_FACTS and (text in _BARE or (fact == "service_name" and _COMPLAINT.search(text))):
            problems.append(f"мусорный факт {fact} = «{value}»")
    if conversation.status in PROGRESS and conversation.summary == VAGUE_TITLE:
        problems.append("заголовок «Проблема требует уточнения»")
    return Result(case["id"], case.get("tags", []), conversation.playbook_id or "", conversation.status,
                  questions, problems, transcript)


def run(path: Path = GOLDEN, engine: TriageEngine | None = None) -> list[Result]:
    cases = yaml.safe_load(path.read_text(encoding="utf-8"))
    db = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(db)
    engine = engine or TriageEngine(KnowledgeBase.load())
    results = []
    with Session(db, expire_on_commit=False) as session:
        service = TriageDialogueService(ConversationRepository(session), engine)
        for case in cases:
            results.append(play(service, case))
    return results


def summary(results: list[Result]) -> dict[str, dict[str, float]]:
    """Share of clean dialogues and mean questions, per tag and overall."""
    groups: dict[str, list[Result]] = {"всего": results}
    for result in results:
        for tag in result.tags:
            groups.setdefault(tag, []).append(result)
    return {
        name: {
            "dialogues": len(items),
            "clean": sum(r.ok for r in items) / len(items),
            "playbook": sum(not any(p.startswith("сценарий") for p in r.problems) for r in items) / len(items),
            "questions": sum(r.questions for r in items) / len(items),
        }
        for name, items in groups.items()
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true", help="print every transcript")
    parser.add_argument("--llm", action="store_true", help="use the provider from the environment")
    parser.add_argument("--semantic", action="store_true",
                        help="add meaning-based matching (needs Ollama with bge-m3)")
    args = parser.parse_args()
    engine = TriageEngine.from_env() if args.llm else None
    if args.semantic:
        from helpflow_ai.understanding.semantic import OllamaEmbedder, SemanticIndex
        knowledge = KnowledgeBase.load()
        url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        engine = TriageEngine(knowledge, semantic=SemanticIndex(OllamaEmbedder(url), knowledge.playbooks,
                                                                background=False))
    results = run(engine=engine)
    for result in results:
        mark = "OK  " if result.ok else "FAIL"
        print(f"[{mark}] {result.id:<24} {result.playbook:<26} вопросов: {result.questions}")
        for problem in result.problems:
            print(f"         - {problem}")
        if args.verbose or not result.ok:
            print("\n".join(result.transcript))
    print()
    for name, row in summary(results).items():
        print(f"{name:<10} диалогов {row['dialogues']:>3}   без замечаний {row['clean']:6.0%}   "
              f"сценарий угадан {row['playbook']:6.0%}   вопросов до действия {row['questions']:.1f}")


if __name__ == "__main__":
    main()
