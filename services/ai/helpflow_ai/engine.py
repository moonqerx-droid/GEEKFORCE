"""TriageEngine — the public entry point used by the backend.

LLM (optional) improves understanding; rules guarantee a valid answer and
own every flow decision, so a failed or hallucinating model cannot break
the dialogue.
"""

from __future__ import annotations

import logging
import re
from threading import RLock
import time
from typing import Any

from pydantic import ValidationError

from . import prompts, rules
from .answer_policy import AnswerPolicy, AnswerRoute
from .evidence import EvidenceValidator
from .knowledge import KnowledgeBase
from .llm import LLMClient, LLMError, LLMSettings
from .understanding import morph
from .understanding.semantic import SemanticIndex, from_env as semantic_from_env
from .retrieval import KnowledgeRetriever
from .schemas import (
    Analysis,
    AnswerKind,
    Citation,
    DetectedIssue,
    ConversationContext,
    Decision,
    DecisionAction,
    EscalationCard,
    GroundedAnswer,
    KnowledgeChunk,
    KnowledgeMatch,
    Playbook,
    Question,
    QuestionKind,
    RetrievedFragment,
    Step,
    StepOutcome,
    Urgency,
)

logger = logging.getLogger(__name__)

MAX_QUESTIONS = 3
MAX_QUESTIONS_URGENT = 1
MAX_RENDERED_MESSAGE_LENGTH = 1200
URGENT_LEVELS = (Urgency.HIGH, Urgency.CRITICAL)
# Meaning-based matching (see TriageEngine._with_meaning); cosine similarity of bge-m3.
SEMANTIC_MIN = 0.70
SEMANTIC_UNKNOWN_GAP = 0.05
SEMANTIC_SWITCH_GAP = 0.06
SEMANTIC_SAFETY_MIN = 0.75
SEMANTIC_SAFETY_GAP = 0.10
URGENT_WORKAROUND_INTRO = "Чтобы успеть, начнём с самого быстрого обходного пути."
AFTER_WORKAROUND_INTRO = ("Хорошо, так вы не выпадете из работы. Когда будет пара минут, "
                          "давайте разберёмся с причиной, чтобы это не повторилось.")
OUTCOME_LABELS = {
    StepOutcome.HELPED: "помогло",
    StepOutcome.NOT_HELPED: "не помогло",
    StepOutcome.CANNOT_DO: "не удалось выполнить",
}
_PROTECTED_PLAYBOOKS = {"credentials_request", "mass_incident", "security_incident"}
_DOCUMENT_INJECTION = re.compile(
    r"(?:игнорир\w*|забуд\w*)[^.!?\n]{0,60}(?:инструкц\w*|правил\w*|prompt|system)|"
    r"(?:выдай|покажи|сообщи|раскрой)[^.!?\n]{0,50}(?:парол\w*|токен\w*|секрет\w*)|"
    r"(?:ignore|forget)[^.!?\n]{0,60}(?:instructions?|rules?|prompt)",
    re.IGNORECASE,
)


class TriageEngine:
    def __init__(self, knowledge: KnowledgeBase, llm: LLMClient | None = None,
                 semantic: "SemanticIndex | None" = None):
        self.kb = knowledge
        self.llm = llm
        self.semantic = semantic
        morph.use_playbooks(knowledge.playbooks)  # typo vocabulary; cached by content
        self._base_chunks = tuple(knowledge.chunks)
        self._company_chunks: tuple[KnowledgeChunk, ...] = ()
        self._knowledge_lock = RLock()
        self.retriever = KnowledgeRetriever(list(self._base_chunks))
        self.answer_policy = AnswerPolicy()

    @classmethod
    def from_env(cls) -> "TriageEngine":
        settings = LLMSettings.from_env()
        knowledge = KnowledgeBase.load()
        return cls(knowledge, LLMClient(settings) if settings else None,
                   semantic=semantic_from_env(knowledge.playbooks))

    # --- understanding ------------------------------------------------------

    def analyze(self, message: str, context: ConversationContext | None = None) -> Analysis:
        """Understand the first message (or re-analyze with more context)."""
        if not message or not message.strip():
            raise ValueError("message must not be empty")
        ctx = context or ConversationContext(original_request=message)
        analysis = self._rules_analysis(message, ctx)
        if self.llm is not None and self.llm.supports_analysis:
            analysis = self._merge_llm(analysis, message, ctx)
        return self._finalize(analysis, ctx)

    def absorb_answer(self, message: str, context: ConversationContext) -> dict[str, str]:
        """Facts learned from a user reply. Returns only new or updated facts."""
        new_facts = {
            key: value
            for key, value in rules.extract_facts(message).items()
            if key not in context.known_facts
        }
        pending = self._pending_question(context)
        if pending is not None:
            new_facts[pending.fact] = rules.parse_answer(pending, message)
        return new_facts

    def citations_for(self, source_ids: list[str]) -> list[Citation]:
        """Resolve persisted source ids into current presentation metadata."""
        with self._knowledge_lock:
            chunks = {chunk.id: chunk for chunk in (*self._base_chunks, *self._company_chunks)}
        return [
            Citation(source_id=source_id, title=chunks[source_id].title, quote=chunks[source_id].text[:1200])
            for source_id in dict.fromkeys(source_ids)
            if source_id.startswith("document:") and source_id in chunks
        ]

    def set_company_fragments(self, fragments: list[RetrievedFragment | dict]) -> None:
        """Atomically replace active READY document fragments supplied by the API.

        The adapter owns lifecycle filtering. Passing an empty list immediately
        removes archived or unavailable company knowledge from retrieval.
        """
        parsed = [RetrievedFragment.model_validate(fragment) for fragment in fragments]
        ids = [fragment.source_id for fragment in parsed]
        duplicates = {source_id for source_id in ids if ids.count(source_id) > 1}
        if duplicates:
            raise ValueError(f"duplicate company fragment ids: {sorted(duplicates)}")
        chunks = tuple(KnowledgeChunk(
            id=fragment.source_id,
            service="Company knowledge",
            title=fragment.title,
            text=fragment.text,
            keywords=[],
            escalation_team="Service Desk L1",
        ) for fragment in parsed)
        with self._knowledge_lock:
            self._company_chunks = chunks
            self.retriever = KnowledgeRetriever([*self._base_chunks, *chunks])

    @staticmethod
    def interpret_confirmation(message: str) -> bool | None:
        """For VERIFYING: True = solved, False = not solved, None = unclear."""
        return rules.parse_confirmation(message)

    @staticmethod
    def is_greeting(message: str) -> bool:
        return rules.is_greeting_only(message)

    @staticmethod
    def conversation_intent(message: str) -> str | None:
        return rules.conversation_intent(message)

    def quick_replies(self, playbook_id: str | None, fact: str) -> list[str]:
        """Buttons for the question that fills `fact`; empty for free-text or unknown ones."""
        if not playbook_id or not self.kb.has(playbook_id):
            return []
        question = next((q for q in self.kb.get(playbook_id).questions if q.fact == fact), None)
        return rules.quick_replies(question) if question else []

    # --- flow ---------------------------------------------------------------

    def decide(self, context: ConversationContext) -> Decision:
        """Choose the flow with rules, then optionally improve only its wording."""
        query = context.original_request or _first_user_message(context)
        if context.playbook_id not in _PROTECTED_PLAYBOOKS:
            matches = self.retriever.search(query, context.playbook_id)
            company = next(
                (match.chunk for match in matches if match.chunk.id.startswith("document:")),
                None,
            )
            if company is not None:
                last = context.completed_steps[-1] if context.completed_steps else None
                if last is not None and last.step_id == f"knowledge.{company.id}":
                    if last.outcome == StepOutcome.HELPED and not context.verification_failed:
                        return Decision(
                            action=DecisionAction.VERIFY,
                            message="Проверьте, пожалуйста: ответ из документа решил ваш вопрос?",
                            reason="ответ по корпоративному документу помог",
                            source_ids=[company.id],
                            answer_kind=AnswerKind.DOCUMENT,
                            citations=[Citation(
                                source_id=company.id,
                                title=company.title,
                                quote=_safe_company_excerpt(company.text),
                            )],
                        )
                    playbook = self.kb.get(context.playbook_id or "unknown")
                    return self._escalate(
                        playbook,
                        "ответ по корпоративному документу не решил вопрос",
                    ).model_copy(update={"playbook_id": playbook.id})
                decision = _company_knowledge_decision(company)
                if (
                    self.llm is not None
                    and self.llm.supports_response_rendering
                    and (
                        not self.llm.prefers_deterministic_playbooks
                        or self.llm.renders_company_answers_synchronously
                    )
                ):
                    return self._render_decision(decision, context)
                return decision
        procedural_route = self.answer_policy.procedural_route(query, context.playbook_id)
        if procedural_route == AnswerRoute.GENERAL:
            return _general_how_to_decision(
                self.answer_policy.general_how_to_topic(query) or "basic"
            )
        if procedural_route == AnswerRoute.OPERATOR:
            playbook = self.kb.get(context.playbook_id)
            return self._escalate(
                playbook,
                "общая рекомендация запрещена без подтверждённого источника",
            ).model_copy(update={"playbook_id": playbook.id})
        decision = self._decide_rules(context)
        if decision.step is not None and decision.step.id.startswith("general."):
            # These tiny, deterministic hints exist specifically to avoid a
            # multi-second model call for reversible first-aid actions.
            return decision
        if self.llm is None or not self.llm.supports_response_rendering:
            return decision
        if self.llm.prefers_deterministic_playbooks:
            query = context.original_request or _first_user_message(context)
            matches = self.retriever.search(query, decision.playbook_id or context.playbook_id)
            route = self.answer_policy.route(
                query,
                matches,
                decision.playbook_id or context.playbook_id,
            )
            if route != AnswerRoute.COMPANY:
                return decision
            if not self.llm.renders_company_answers_synchronously:
                return decision
        return self._render_decision(decision, context)

    def _decide_rules(self, context: ConversationContext) -> Decision:
        # Facts stated in the first message count as known even if the caller lost them.
        stated = rules.extract_facts(context.original_request) if context.original_request else {}
        context = context.model_copy(update={"known_facts": {**stated, **context.known_facts}})
        plan = self._issue_plan(context)
        index, needs_check = self._progress(plan, context)
        last = context.completed_steps[-1] if context.completed_steps else None
        after_workaround = bool(last and self._is_workaround(last.step_id))
        if (
            last
            and last.step_id.startswith("general.")
            and last.outcome == StepOutcome.HELPED
            and not context.verification_failed
        ):
            return Decision(
                action=DecisionAction.VERIFY,
                message="Проверьте, пожалуйста: проблема решена и всё работает как нужно?",
                reason="общая безопасная рекомендация помогла",
                playbook_id="unknown",
                answer_kind=AnswerKind.GENERAL,
            )
        solved = bool(last and last.outcome == StepOutcome.HELPED and not context.verification_failed
                      and not after_workaround)
        if solved and index is None:
            playbook = self._step_owner(last.step_id) or self.kb.get(plan[0].playbook_id)
            return Decision(
                action=DecisionAction.VERIFY,
                message=playbook.verify_question,
                reason="пользователь сообщил, что шаг помог",
                playbook_id=playbook.id,
                answer_kind=AnswerKind.PLAYBOOK,
            )
        if index is None:
            # "Not solved" at verification: keep working on the problem of the last step.
            index = self._owner_index(plan, last.step_id) if last else 0
        issue = plan[index]
        if needs_check:
            question = _check_question(issue)
            return Decision(action=DecisionAction.ASK, message=question.text, question=question,
                            reason=f"проверяем, осталась ли проблема: {issue.title}",
                            playbook_id=issue.playbook_id, answer_kind=AnswerKind.PLAYBOOK)
        playbook = self.kb.get(issue.playbook_id)
        decision = self._work_on(playbook, context, last, after_workaround)
        if len(plan) > 1 and not context.asked_facts and not context.completed_steps:
            decision = decision.model_copy(update={"message": f"{_plan_intro(plan)} {decision.message}"})
        return decision.model_copy(update={"playbook_id": playbook.id})

    def _work_on(self, playbook: Playbook, context: ConversationContext, last, after_workaround: bool) -> Decision:
        """Next action for one problem: workaround, question, step or hand-off."""
        if playbook.id == "unknown":
            query = context.original_request or _first_user_message(context)
            if last is not None and last.step_id.startswith("general."):
                return self._escalate(playbook, "общий совет не помог")
            matches = self.retriever.search(query, playbook.id)
            route = self.answer_policy.route(query, matches, playbook.id)
            if route == AnswerRoute.GENERAL:
                return _general_guidance_decision(query)
            if route == AnswerRoute.COMPANY:
                company = next(
                    match.chunk for match in matches if match.chunk.id.startswith("document:")
                )
                return _company_knowledge_decision(company)
            if route == AnswerRoute.OPERATOR and self.answer_policy.requires_verified_source(query):
                return self._escalate(
                    playbook,
                    "нет подтверждённого источника для безопасного ответа",
                )
        if context.urgency in URGENT_LEVELS:
            workaround = next((s for s in _open_steps(playbook, context) if s.workaround), None)
            if workaround is not None:
                return _step_decision(workaround, URGENT_WORKAROUND_INTRO,
                                      "срочно: сначала быстрый обходной путь")
        subject = rules.detect_subject(_user_text(context)) if playbook.id == "unknown" else None
        if subject:
            # No playbook for a named thing: extra questions would not change anything.
            decision = self._escalate(playbook, f"нет сценария в базе знаний для: {subject}")
            note = (f"Готового решения для такой проблемы у меня нет (тема: {subject}), поэтому "
                    "не буду мучить вас лишними вопросами.")
            return decision.model_copy(update={"message": f"{note} {decision.message}"})
        question = self.next_question(playbook, context)
        if question is not None:
            return Decision(action=DecisionAction.ASK, message=question.text, question=question,
                            reason=f"не хватает факта: {question.fact}",
                            answer_kind=AnswerKind.PLAYBOOK)
        if playbook.id == "unknown":
            return self._escalate(playbook, "не найден подтверждённый сценарий в базе знаний")
        if playbook.escalate_immediately:
            return self._escalate(playbook, "сценарий требует участия специалиста")
        described = _described_symptoms(playbook, context)
        if described & set(playbook.escalate_on_symptoms):
            return self._escalate(playbook, "решить может только специалист: " + ", ".join(sorted(
                described & set(playbook.escalate_on_symptoms))), context.known_facts)
        step = self.next_step(playbook, context)
        if step is not None:
            helped = after_workaround and last.outcome == StepOutcome.HELPED
            return _step_decision(step, AFTER_WORKAROUND_INTRO if helped else "",
                                  "следующий подходящий шаг сценария")
        tried = len(context.completed_steps)
        return self._escalate(playbook, f"выполнено шагов: {tried}, проблема не решена")

    def _render_decision(self, decision: Decision, context: ConversationContext) -> Decision:
        playbook = self.kb.get(decision.playbook_id or context.playbook_id)
        query = context.original_request or _first_user_message(context)
        matches = self.retriever.search(query, playbook.id)
        if not matches:
            return decision.model_copy(update={"fallback_reason": "no_sources"})
        started = time.monotonic()
        try:
            raw = self.llm.chat_json(
                prompts.RESPONSE_SYSTEM,
                prompts.build_grounded_response_user(decision, playbook, matches),
            )
            answer = GroundedAnswer.model_validate(raw)
            elapsed = _elapsed_ms(started)
            if answer.needs_operator != (decision.action == DecisionAction.ESCALATE):
                return decision.model_copy(update={
                    "fallback_reason": "action_mismatch",
                    "llm_latency_ms": elapsed,
                })
            validation = EvidenceValidator().validate(
                answer,
                matches,
                prepared_message=decision.message,
            )
            if not validation.accepted:
                return decision.model_copy(update={
                    "fallback_reason": validation.reason,
                    "llm_latency_ms": elapsed,
                })
            message = answer.answer.strip()
            notice = playbook.safety_notice
            if notice and notice in decision.message and notice not in message:
                message = f"{notice} {message}"
            if len(message) > MAX_RENDERED_MESSAGE_LENGTH:
                return decision.model_copy(update={
                    "fallback_reason": "message_too_long",
                    "llm_latency_ms": elapsed,
                })
            return decision.model_copy(update={
                "message": message,
                "message_source": "llm",
                "source_ids": validation.source_ids,
                "citations": _answer_citations(answer, matches),
                "llm_latency_ms": elapsed,
            })
        except ValidationError as error:
            logger.warning("LLM response validation failed, using rules: %s", error)
            return decision.model_copy(update={
                "fallback_reason": "invalid_response",
                "llm_latency_ms": _elapsed_ms(started),
            })
        except (LLMError, ValueError, TypeError) as error:
            logger.warning("LLM response rendering failed, using rules: %s", error)
            return decision.model_copy(update={
                "fallback_reason": "llm_error",
                "llm_latency_ms": _elapsed_ms(started),
            })

    def next_question(self, playbook: Playbook, context: ConversationContext) -> Question | None:
        limit = MAX_QUESTIONS_URGENT if context.urgency in URGENT_LEVELS else MAX_QUESTIONS
        own_facts = {q.fact for q in playbook.questions}
        if len([fact for fact in context.asked_facts if fact in own_facts]) >= limit:
            return None
        for question in _applicable_questions(playbook, context):
            if question.fact not in context.known_facts and question.fact not in context.asked_facts:
                return question
        return None

    @staticmethod
    def next_step(playbook: Playbook, context: ConversationContext) -> Step | None:
        return next(_open_steps(playbook, context), None)

    def _is_workaround(self, step_id: str) -> bool:
        return any(step.id == step_id and step.workaround for pb in self.kb.playbooks for step in pb.steps)

    # --- several problems in one request -------------------------------------

    def _issue_plan(self, ctx: ConversationContext) -> list[DetectedIssue]:
        """Problems of this dialogue in handling order; the dialogue's playbook is first.

        Derived from the first message on every call, so the backend keeps no extra state.
        """
        primary = self.kb.get(ctx.playbook_id)
        request = ctx.original_request.strip()
        found = self._detect_issues(request, primary, ctx.urgency)
        if primary.id not in {issue.playbook_id for issue in found}:
            return [self._issue(primary.id, "", request)]
        return sorted(found, key=lambda issue: issue.playbook_id != primary.id)

    def _detect_issues(self, request: str, best: Playbook, urgency: Urgency | None) -> list[DetectedIssue]:
        """All problems of the request in the order to handle them (root cause first)."""
        if not request or best.id in (*rules.PRIORITY_PLAYBOOKS, "unknown") or best.escalate_immediately:
            return [self._issue(best.id, "", request)]
        # `best` is what analysis chose (keywords, possibly corrected by meaning); clauses
        # that mention it belong to it.
        found = rules.plan_issues(request, self.kb.playbooks, best.id, urgency in URGENT_LEVELS)
        return [self._issue(pid, evidence, request) for pid, evidence in found]

    def _issue(self, playbook_id: str, evidence: str, request: str) -> DetectedIssue:
        playbook = self.kb.get(playbook_id)
        text = evidence or request
        return DetectedIssue(
            playbook_id=playbook.id,
            title=playbook.title,
            service=rules.detect_service(text, playbook) if text else playbook.service,
            symptoms=rules.detect_symptoms(text, playbook),
            evidence=evidence,
        )

    def _progress(self, plan: list[DetectedIssue], ctx: ConversationContext) -> tuple[int | None, bool]:
        """Index of the first unsolved problem (None = all solved) and whether to first
        ask if it is still there: fixing the previous one may have fixed it too."""
        for index, issue in enumerate(plan):
            playbook = self.kb.get(issue.playbook_id)
            answer = ctx.known_facts.get(_check_fact(playbook.id))
            if answer == "yes":
                continue
            step_ids = {step.id for step in playbook.steps}
            own = [r for r in ctx.completed_steps if r.step_id in step_ids and not self._is_workaround(r.step_id)]
            if own and own[-1].outcome == StepOutcome.HELPED:
                continue
            started = any(r.step_id in step_ids for r in ctx.completed_steps)
            needs_check = (index > 0 and answer is None and not started
                           and _check_fact(playbook.id) not in ctx.asked_facts)
            return index, needs_check
        return None, False

    def _step_owner(self, step_id: str) -> Playbook | None:
        return next((pb for pb in self.kb.playbooks if any(s.id == step_id for s in pb.steps)), None)

    def _owner_index(self, plan: list[DetectedIssue], step_id: str) -> int:
        owner = self._step_owner(step_id)
        return next((i for i, issue in enumerate(plan) if owner and issue.playbook_id == owner.id), 0)

    def _issue_statuses(self, plan: list[DetectedIssue], ctx: ConversationContext) -> list[DetectedIssue]:
        index, needs_check = self._progress(plan, ctx)
        last = ctx.completed_steps[-1] if ctx.completed_steps else None
        if index is None:
            index = self._owner_index(plan, last.step_id) if last and ctx.verification_failed else len(plan)
        statuses = []
        for i, issue in enumerate(plan):
            status = "resolved" if i < index else "pending" if i > index or needs_check else "in_progress"
            statuses.append(issue.model_copy(update={"status": status}))
        return statuses

    def _question_for_fact(self, ctx: ConversationContext, fact: str) -> Question | None:
        plan = self._issue_plan(ctx)
        for issue in plan:
            if fact == _check_fact(issue.playbook_id):
                return _check_question(issue)
        playbooks = [self.kb.get(issue.playbook_id) for issue in plan] + self.kb.playbooks
        return next((q for pb in playbooks for q in pb.questions if q.fact == fact), None)

    # --- escalation ---------------------------------------------------------

    def build_escalation_card(self, context: ConversationContext, reason: str = "") -> EscalationCard:
        request = context.original_request or _first_user_message(context)
        context = context.model_copy(update={"original_request": request})
        issues = self._issue_statuses(self._issue_plan(context), context)
        current = next((i for i in issues if i.status == "in_progress"), issues[0])
        # The team of the problem the dialogue stopped on.
        playbook = self.kb.get(current.playbook_id)
        analysis = self._rules_analysis(request, context) if request.strip() else None
        urgency = analysis.urgency if analysis else playbook.default_urgency
        card = EscalationCard(
            original_request=request,
            summary=analysis.summary if analysis else playbook.title,
            service=analysis.service if analysis else playbook.service,
            urgency=rules.max_urgency(urgency, context.urgency or urgency),
            urgency_reason=analysis.urgency_reason if analysis else "",
            known_facts=dict(context.known_facts),
            questions_and_answers=self._questions_and_answers(context),
            performed_steps=self._performed_steps(context),
            current_result=self._current_result(context),
            escalation_reason=reason or "автоматическое решение не помогло",
            recommended_team=playbook.escalation_team,
            ai_summary="",
            issues=issues,
        )
        ai_summary, source = self._ai_summary(card)
        return card.model_copy(update={"ai_summary": ai_summary, "source": source})

    # --- internals ----------------------------------------------------------

    def _with_meaning(self, text: str, found: rules.Classification) -> rules.Classification:
        """Let the embedding model correct the keywords when it is clearly more certain.

        Thresholds come from the golden dialogues: where the two disagree, the model is
        right when it leads by a margin and wrong only when its lead is tiny. Keyword
        safety scenarios are never overridden, and a mass outage is never inferred from
        meaning alone (it needs «у всех»-type evidence).
        """
        ranked = self.semantic.rank(text) if self.semantic is not None else None
        if not ranked:
            return found
        top, best = ranked[0]
        gap = best - (ranked[1][1] if len(ranked) > 1 else 0.0)
        if found.playbook_id in rules.PRIORITY_PLAYBOOKS or top == "mass_incident" or top == found.playbook_id:
            return found
        if top in rules.PRIORITY_PLAYBOOKS:
            confident = best >= SEMANTIC_SAFETY_MIN and gap >= SEMANTIC_SAFETY_GAP
            return rules.Classification(top, 0.9) if confident else found
        if found.playbook_id == "unknown":
            confident = best >= SEMANTIC_MIN and gap >= SEMANTIC_UNKNOWN_GAP
        else:
            confident = (best >= SEMANTIC_MIN and gap >= SEMANTIC_SWITCH_GAP
                         and found.confidence < 0.9)
        return rules.Classification(top, round(min(0.95, best), 2)) if confident else found

    def _rules_analysis(self, message: str, ctx: ConversationContext) -> Analysis:
        original = ctx.original_request.strip()
        text = message if not original or original == message.strip() else f"{original} {message}"
        keep_playbook = ctx.playbook_id and self.kb.has(ctx.playbook_id)
        classification = rules.classify(text, self.kb.playbooks)
        if not keep_playbook:
            classification = self._with_meaning(text, classification)
        playbook = self.kb.get(ctx.playbook_id if keep_playbook else classification.playbook_id)
        urgency, reason = rules.detect_urgency(text, playbook)
        if keep_playbook:
            plan = self._issue_plan(ctx.model_copy(update={"original_request": text}))
        else:
            plan = self._detect_issues(text, playbook, urgency)
        if not keep_playbook and plan[0].playbook_id != playbook.id:
            # Several problems: start with the root cause, keep the most urgent level.
            first = self.kb.get(plan[0].playbook_id)
            first_urgency, first_reason = rules.detect_urgency(text, first)
            if rules.URGENCY_ORDER.index(first_urgency) >= rules.URGENCY_ORDER.index(urgency):
                urgency, reason = first_urgency, first_reason
            playbook = first
            plan = [plan[0], *[i for i in plan[1:] if i.playbook_id != first.id]]
        service = rules.detect_service(text, playbook)
        if playbook.id == "slow_performance" and service == playbook.service:
            service = rules.detect_subject(text) or service  # «эксель тормозит» → Excel
        symptoms = rules.detect_symptoms(text, playbook)
        stated = rules.extract_facts(text)
        subject = rules.detect_subject(text) if playbook.id == "unknown" else None
        if subject:
            service = subject
            stated.setdefault("service_name", subject)
        additional = [issue for issue in plan if issue.playbook_id != playbook.id]
        summary = _summary(playbook, service, symptoms, text)
        if additional:
            summary += ". Ещё: " + "; ".join(i.evidence or i.title for i in additional)
        return Analysis(
            summary=summary,
            service=service,
            symptoms=symptoms,
            urgency=urgency,
            urgency_reason=reason,
            known_facts={**stated, **ctx.known_facts},
            confidence=classification.confidence,
            recommended_playbook=playbook.id,
            source="rules",
            additional_issues=additional,
        )

    def _merge_llm(self, base: Analysis, message: str, ctx: ConversationContext) -> Analysis:
        try:
            raw = self.llm.chat_json(
                prompts.build_analysis_system(self.kb.playbooks),
                prompts.build_analysis_user(message, ctx),
            )
            llm = _coerce_llm_analysis(raw, base)
        except (LLMError, ValidationError, ValueError, TypeError) as error:
            logger.warning("LLM analysis failed, using rules: %s", error)
            return base
        # Safety-critical rule matches and an ongoing dialogue's playbook are never overridden.
        keep_rules = base.recommended_playbook in rules.PRIORITY_PLAYBOOKS or bool(ctx.playbook_id)
        use_llm_playbook = not keep_rules and self.kb.has(llm.recommended_playbook)
        urgency = rules.max_urgency(base.urgency, llm.urgency)  # never downgrade
        reason = llm.urgency_reason if urgency == llm.urgency and llm.urgency_reason else base.urgency_reason
        llm_facts = {k: v for k, v in llm.known_facts.items() if k not in base.known_facts}
        return base.model_copy(update={
            "summary": llm.summary,
            "service": llm.service or base.service,
            "symptoms": llm.symptoms or base.symptoms,
            "urgency": urgency,
            "urgency_reason": reason,
            "known_facts": {**base.known_facts, **llm_facts},
            "recommended_playbook": llm.recommended_playbook if use_llm_playbook else base.recommended_playbook,
            "confidence": llm.confidence,
            "source": "llm",
        })

    def _finalize(self, analysis: Analysis, ctx: ConversationContext) -> Analysis:
        playbook = self.kb.get(analysis.recommended_playbook)
        flow_ctx = ctx.model_copy(update={"known_facts": analysis.known_facts, "urgency": analysis.urgency})
        missing = [q.fact for q in _applicable_questions(playbook, flow_ctx) if q.fact not in analysis.known_facts]
        question = self.next_question(playbook, flow_ctx)
        return analysis.model_copy(update={
            "additional_issues": [
                i for i in analysis.additional_issues if i.playbook_id != analysis.recommended_playbook
            ],
            "missing_facts": missing,
            "next_question": question.text if question else None,
            "should_escalate": playbook.escalate_immediately,
        })

    def _pending_question(self, ctx: ConversationContext) -> Question | None:
        if not ctx.asked_facts:
            return None
        fact = ctx.asked_facts[-1]
        if fact in ctx.known_facts:
            return None
        return self._question_for_fact(ctx, fact)

    @staticmethod
    def _escalate(playbook: Playbook, reason: str, facts: dict[str, str] | None = None) -> Decision:
        text = (f"Передаю обращение специалисту ({playbook.escalation_team}). "
                "Всё, что мы выяснили, уже в заявке — повторять ничего не придётся.")
        if playbook.escalation_note:
            note = playbook.escalation_note.format_map(_FactsOrDash(facts or {}))
            text = f"{note} {text}"
        if playbook.safety_notice:
            text = f"{playbook.safety_notice} {text}"
        return Decision(action=DecisionAction.ESCALATE, message=text, reason=reason,
                        escalation_team=playbook.escalation_team,
                        answer_kind=AnswerKind.HANDOFF)

    def _questions_and_answers(self, ctx: ConversationContext) -> list[dict[str, str]]:
        answers = []
        for fact in ctx.asked_facts:
            question = self._question_for_fact(ctx, fact)
            answers.append({"question": question.text if question else fact,
                            "answer": ctx.known_facts.get(fact, "нет ответа")})
        return answers

    def _step_title(self, step_id: str) -> str:
        owner = self._step_owner(step_id)
        return next((s.title for s in owner.steps if s.id == step_id), step_id) if owner else step_id

    def _performed_steps(self, ctx: ConversationContext) -> list[dict[str, str]]:
        return [
            {"step_id": r.step_id, "step": self._step_title(r.step_id), "result": OUTCOME_LABELS[r.outcome]}
            for r in ctx.completed_steps
        ]

    def _current_result(self, ctx: ConversationContext) -> str:
        if not ctx.completed_steps:
            return "Проблема не решена, шаги самостоятельного решения не выполнялись"
        last = ctx.completed_steps[-1]
        verdict = "не подтверждено пользователем" if ctx.verification_failed else OUTCOME_LABELS[last.outcome]
        return (f"Проблема не решена после {len(ctx.completed_steps)} шаг(ов); "
                f"последний шаг «{self._step_title(last.step_id)}» — {verdict}")

    def _ai_summary(self, card: EscalationCard) -> tuple[str, str]:
        if self.llm is not None and self.llm.supports_summaries:
            try:
                raw = self.llm.chat_json(prompts.SUMMARY_SYSTEM,
                                         prompts.build_summary_user(card.model_dump(mode="json")))
                summary = str(raw.get("ai_summary", "")).strip()
                if summary:
                    return summary, "llm"
            except LLMError as error:
                logger.warning("LLM summary failed, using template: %s", error)
        return _template_summary(card), "rules"


ROOT_CAUSE_INTROS = {
    "network_wifi": "Начнём с интернета: когда он сбоит, почта и звонки тоже часто барахлят.",
    "vpn_connection": "Начнём с VPN: без него рабочие сервисы тоже могут не открываться.",
}


def _check_fact(playbook_id: str) -> str:
    return f"issue_resolved.{playbook_id}"


def _check_question(issue: DetectedIssue) -> Question:
    what = issue.evidence or issue.title
    return Question(
        fact=_check_fact(issue.playbook_id),
        text=f"С этим разобрались! Теперь следующая проблема — «{what}». Сейчас с этим всё в порядке?",
        kind=QuestionKind.YES_NO,
    )


def _plan_intro(plan: list[DetectedIssue]) -> str:
    listed = "; ".join(issue.evidence or issue.title for issue in plan)
    why = ROOT_CAUSE_INTROS.get(plan[0].playbook_id, "Начнём с первой.")
    return f"Вижу сразу несколько проблем: {listed}. {why} Остальное разберём следом, ничего не потеряется."


class _FactsOrDash(dict):
    def __missing__(self, key: str) -> str:
        return "—"


def _user_text(ctx: ConversationContext) -> str:
    """Everything the user wrote: symptoms may come from the first message or later answers."""
    parts = [ctx.original_request] if ctx.original_request else []
    parts += [str(m.get("content", "")) for m in ctx.messages if m.get("role") == "user"]
    return " ".join(dict.fromkeys(p.strip() for p in parts if p and p.strip()))


def _described_symptoms(playbook: Playbook, ctx: ConversationContext) -> set[str]:
    return set(rules.detect_symptoms(_user_text(ctx), playbook))


def _symptoms_allow(item: Question | Step, described: set[str]) -> bool:
    if item.when_symptoms and not described & set(item.when_symptoms):
        return False
    return not described & set(item.unless_symptoms)


def _applicable_questions(playbook: Playbook, ctx: ConversationContext) -> list[Question]:
    described = _described_symptoms(playbook, ctx)
    return [
        q for q in playbook.questions
        if _symptoms_allow(q, described) and not (q.only_without_symptoms and described)
        and all(ctx.known_facts.get(key) in values for key, values in q.when_facts.items())
    ]


def _open_steps(playbook: Playbook, ctx: ConversationContext):
    """Steps not tried yet whose fact and symptom conditions hold, in playbook order."""
    done = {record.step_id for record in ctx.completed_steps}
    facts = ctx.known_facts
    described = _described_symptoms(playbook, ctx)
    for step in playbook.steps:
        if step.id in done or not _symptoms_allow(step, described):
            continue
        if any(facts.get(key) not in values for key, values in step.when.items()):
            continue
        if any(facts.get(key) in values for key, values in step.unless.items()):
            continue
        yield step


def _step_decision(step: Step, intro: str, reason: str) -> Decision:
    text = f"{step.title}. {step.instruction}"
    return Decision(action=DecisionAction.STEP, message=f"{intro} {text}" if intro else text,
                    step=step, reason=reason, answer_kind=AnswerKind.PLAYBOOK)


def _general_guidance_decision(query: str) -> Decision:
    normalized = query.casefold()
    if "кэш" in normalized or "cache" in normalized or "cookie" in normalized:
        step_id = "general.browser_cache"
        instruction = (
            "Сначала сохраните несохранённые данные и обновите страницу. Если не поможет, "
            "очистите кэш только для проблемного сайта и войдите заново; сохранённые пароли "
            "и данные других сайтов не удаляйте."
        )
    elif "wi-fi" in normalized or "wifi" in normalized or "интернет" in normalized:
        step_id = "general.connection"
        instruction = (
            "Проверьте, открывается ли другой сайт, затем отключитесь от сети и подключитесь "
            "снова. Не меняйте системные сетевые настройки и корпоративные сертификаты."
        )
    elif "обнов" in normalized and "страниц" in normalized:
        step_id = "general.refresh"
        instruction = "Сохраните введённые данные и выполните обычное обновление страницы."
    elif "перезапуст" in normalized or "перезагруз" in normalized:
        step_id = "general.restart"
        instruction = (
            "Сохраните работу, полностью закройте проблемное приложение и откройте его снова."
        )
    else:
        step_id = "general.basic_check"
        instruction = (
            "Сохраните работу, проверьте подключение и один раз перезапустите проблемное "
            "приложение. Не устанавливайте программы и не меняйте системные настройки."
        )
    prefix = "Общая рекомендация — не правило компании."
    step = Step(id=step_id, title="Базовая проверка", instruction=instruction)
    return Decision(
        action=DecisionAction.STEP,
        message=f"{prefix} {instruction}",
        step=step,
        reason="низкорисковая обратимая общая рекомендация",
        answer_kind=AnswerKind.GENERAL,
    )


def _company_knowledge_decision(chunk: KnowledgeChunk) -> Decision:
    quote = _safe_company_excerpt(chunk.text)
    if not quote:
        return Decision(
            action=DecisionAction.ESCALATE,
            message=(
                "В найденном документе есть непроверяемые управляющие инструкции, поэтому "
                "я не буду использовать его как ответ и передам вопрос специалисту."
            ),
            reason="корпоративный фрагмент отклонён safety gate",
            answer_kind=AnswerKind.HANDOFF,
        )
    # Render Markdown as readable chat text while keeping the evidence quote verbatim.
    instruction = re.sub(r"\n{2,}", "\n", re.sub(r"(?m)^#{1,6}\s+", "", quote)).strip()
    step = Step(
        id=f"knowledge.{chunk.id}",
        title=f"По документу «{chunk.title}»",
        instruction=instruction,
    )
    return Decision(
        action=DecisionAction.STEP,
        message=f"По документу «{chunk.title}»: {instruction}",
        step=step,
        reason="найден подтверждённый документ компании",
        source_ids=[chunk.id],
        answer_kind=AnswerKind.DOCUMENT,
        # The citation stays verbatim: it is the evidence.
        citations=[Citation(source_id=chunk.id, title=chunk.title, quote=quote)],
    )


def _safe_company_excerpt(text: str) -> str:
    """Return one verbatim span while excluding every assistant-control line."""
    source = text.strip()
    safe_blocks: list[str] = []
    current: list[str] = []
    for line in source.splitlines(keepends=True):
        if _DOCUMENT_INJECTION.search(line):
            if current:
                safe_blocks.append("".join(current).strip())
                current = []
            continue
        current.append(line)
    if current:
        safe_blocks.append("".join(current).strip())
    excerpt = max((block for block in safe_blocks if block), key=len, default="")
    if len(excerpt) <= 900:
        return excerpt
    return excerpt[:900].rsplit(" ", 1)[0].rstrip() or excerpt[:900]


def _answer_citations(answer: GroundedAnswer, matches: list[KnowledgeMatch]) -> list[Citation]:
    titles = {match.chunk.id: match.chunk.title for match in matches}
    citations: list[Citation] = []
    seen: set[tuple[str, str]] = set()
    for claim in answer.claims:
        key = (claim.source_id, claim.quote)
        if (
            claim.source_id.startswith("document:")
            and claim.source_id in titles
            and key not in seen
        ):
            citations.append(Citation(
                source_id=claim.source_id,
                title=titles[claim.source_id],
                quote=claim.quote,
            ))
            seen.add(key)
    return citations


def _general_how_to_decision(topic: str) -> Decision:
    guides = {
        "outlook_auto_reply": (
            "general.how_to.outlook_auto_reply",
            "В Outlook откройте «Файл» → «Автоматические ответы», включите их, задайте период "
            "и текст сообщения. В веб-версии этот пункт обычно находится в «Настройки» → "
            "«Почта» → «Автоматические ответы»; названия могут немного отличаться по версии.",
        ),
        "teams_background": (
            "general.how_to.teams_background",
            "До звонка или во время него откройте «Дополнительно» → «Видеоэффекты и параметры», "
            "выберите размытие либо стандартный фон и проверьте предпросмотр перед применением.",
        ),
        "excel_freeze": (
            "general.how_to.excel_freeze",
            "В Excel откройте вкладку «Вид» → «Закрепить области» и выберите «Закрепить верхнюю "
            "строку». Это изменение можно отменить через тот же пункт меню.",
        ),
        "print_pdf": (
            "general.how_to.print_pdf",
            "Откройте системное окно «Печать» и выберите сохранение в PDF или виртуальный принтер "
            "PDF. Перед сохранением проверьте диапазон страниц и не включайте конфиденциальные листы.",
        ),
        "wallpaper": (
            "general.how_to.wallpaper",
            "Откройте системные настройки «Персонализация» или «Обои», выберите изображение и "
            "способ заполнения экрана. Если настройка заблокирована организацией, не обходите "
            "ограничение — обратитесь к специалисту.",
        ),
        "zip_folder": (
            "general.how_to.zip_folder",
            "Нажмите папку правой кнопкой и выберите встроенное действие «Сжать» или «Отправить» → "
            "«Сжатая ZIP-папка». Не помещайте в архив пароли и секреты; исходная папка сохранится.",
        ),
        "shared_calendar": (
            "general.how_to.shared_calendar",
            "В разделе «Календарь» Outlook выберите добавление или открытие общего календаря и "
            "найдите владельца по имени. Если календарь не открывается, владелец должен предоставить "
            "доступ — помощник не может менять права самостоятельно.",
        ),
    }
    step_id, instruction = guides[topic]
    prefix = "Общая рекомендация — не правило компании."
    step = Step(id=step_id, title="Безопасная инструкция", instruction=instruction)
    return Decision(
        action=DecisionAction.STEP,
        message=f"{prefix} {instruction}",
        step=step,
        reason=f"разрешённый низкорисковый how-to: {topic}",
        answer_kind=AnswerKind.GENERAL,
    )


def _summary(playbook: Playbook, service: str, symptoms: list[str], text: str = "") -> str:
    if playbook.id == "service_unavailable":
        title = f"Недоступен сервис {service}"
    elif playbook.id == "slow_performance":
        # «Медленно работает 1С» says it all; the symptom would only repeat it.
        whole = "весь компьютер" in symptoms
        return f"Медленно работает {service}" if service != playbook.service else (
            "Медленно работает компьютер" if whole else playbook.title)
    elif playbook.id == "unknown" and service != playbook.service:
        title = f"Проблема: {service} (готового сценария нет)"
    elif playbook.id == "unknown" and _excerpt(text):
        # The employee's own words say more than «Проблема требует уточнения».
        return _excerpt(text)
    else:
        title = playbook.title
    title_words = _words(title)
    # "VPN не подключается" adds nothing to "Не подключается VPN": same words, other order.
    extra = [s for s in symptoms if not _words(s) <= title_words]
    return f"{title}: {', '.join(extra)}" if extra else title


def _excerpt(text: str, limit: int = 70) -> str:
    """First sentence of the request as a title: «Странная штука с компьютером»."""
    first = re.split(r"(?<=[.!?\n])\s+", text.strip(), maxsplit=1)[0].strip(" .!?,;:")
    if len(first) > limit:
        first = first[:limit].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
    return first[:1].upper() + first[1:]


def _words(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.lower()))


def _first_user_message(ctx: ConversationContext) -> str:
    return next((str(m.get("content", "")) for m in ctx.messages if m.get("role") == "user"), "")


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.monotonic() - started) * 1000))


def _coerce_llm_analysis(raw: dict[str, Any], base: Analysis) -> Analysis:
    facts = raw.get("known_facts")
    symptoms = raw.get("symptoms")
    cleaned = {
        **raw,
        "summary": raw.get("summary") or base.summary,
        "service": raw.get("service") or base.service,
        "recommended_playbook": raw.get("recommended_playbook") or base.recommended_playbook,
        "known_facts": {str(k): str(v) for k, v in facts.items() if v not in (None, "")}
        if isinstance(facts, dict) else {},
        "symptoms": [str(s) for s in symptoms if s] if isinstance(symptoms, list) else [],
        "confidence": min(1.0, max(0.0, float(raw.get("confidence", base.confidence)))),
    }
    allowed = set(Analysis.model_fields)
    return Analysis.model_validate({k: v for k, v in cleaned.items() if k in allowed})


def _template_summary(card: EscalationCard) -> str:
    reason = f" ({card.urgency_reason})" if card.urgency_reason else ""
    parts = [f"{card.summary}. Сервис: {card.service}. Срочность: {card.urgency.value}{reason}."]
    if card.known_facts:
        parts.append("Известно: " + "; ".join(f"{k}: {v}" for k, v in card.known_facts.items()) + ".")
    if card.performed_steps:
        parts.append("Выполнено: " + "; ".join(f"{s['step']} — {s['result']}" for s in card.performed_steps) + ".")
    others = card.issues[1:]
    if others:
        labels = {"pending": "не разбирали", "in_progress": "в работе", "resolved": "решено"}
        parts.append("Другие проблемы из обращения: " + "; ".join(
            f"{i.evidence or i.title} — {labels[i.status]}" for i in others) + ".")
    parts.append(f"Текущий результат: {card.current_result}.")
    parts.append(f"Причина передачи: {card.escalation_reason}.")
    return " ".join(parts)
