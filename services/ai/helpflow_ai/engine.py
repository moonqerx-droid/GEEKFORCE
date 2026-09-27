"""TriageEngine — the public entry point used by the backend.

LLM (optional) improves understanding; rules guarantee a valid answer and
own every flow decision, so a failed or hallucinating model cannot break
the dialogue.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from pydantic import ValidationError

from . import prompts, rules
from .knowledge import KnowledgeBase
from .llm import LLMClient, LLMError, LLMSettings
from .retrieval import KnowledgeRetriever
from .schemas import (
    Analysis,
    ConversationContext,
    Decision,
    DecisionAction,
    EscalationCard,
    GroundedAnswer,
    Playbook,
    Question,
    Step,
    StepOutcome,
    Urgency,
)

logger = logging.getLogger(__name__)

MAX_QUESTIONS = 3
MAX_QUESTIONS_URGENT = 1
MAX_RENDERED_MESSAGE_LENGTH = 1200
URGENT_LEVELS = (Urgency.HIGH, Urgency.CRITICAL)
OUTCOME_LABELS = {
    StepOutcome.HELPED: "помогло",
    StepOutcome.NOT_HELPED: "не помогло",
    StepOutcome.CANNOT_DO: "не удалось выполнить",
}


class TriageEngine:
    def __init__(self, knowledge: KnowledgeBase, llm: LLMClient | None = None):
        self.kb = knowledge
        self.llm = llm
        self.retriever = KnowledgeRetriever(knowledge.chunks)

    @classmethod
    def from_env(cls) -> "TriageEngine":
        settings = LLMSettings.from_env()
        return cls(KnowledgeBase.load(), LLMClient(settings) if settings else None)

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

    # --- flow ---------------------------------------------------------------

    def decide(self, context: ConversationContext) -> Decision:
        """Choose the flow with rules, then optionally improve only its wording."""
        decision = self._decide_rules(context)
        if self.llm is None or not self.llm.supports_response_rendering:
            return decision
        return self._render_decision(decision, context)

    def _decide_rules(self, context: ConversationContext) -> Decision:
        playbook = self.kb.get(context.playbook_id)
        last = context.completed_steps[-1] if context.completed_steps else None
        if last and last.outcome == StepOutcome.HELPED and not context.verification_failed:
            return Decision(
                action=DecisionAction.VERIFY,
                message=playbook.verify_question,
                reason="пользователь сообщил, что шаг помог",
            )
        question = self.next_question(playbook, context)
        if question is not None:
            return Decision(action=DecisionAction.ASK, message=question.text, question=question,
                            reason=f"не хватает факта: {question.fact}")
        if playbook.escalate_immediately:
            return self._escalate(playbook, "сценарий требует участия специалиста")
        step = self.next_step(playbook, context)
        if step is not None:
            return Decision(action=DecisionAction.STEP, message=f"{step.title}. {step.instruction}",
                            step=step, reason="следующий подходящий шаг сценария")
        tried = len(context.completed_steps)
        return self._escalate(playbook, f"выполнено шагов: {tried}, проблема не решена")

    def _render_decision(self, decision: Decision, context: ConversationContext) -> Decision:
        playbook = self.kb.get(context.playbook_id)
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
            allowed = {match.chunk.id for match in matches}
            if not set(answer.source_ids) <= allowed:
                return decision.model_copy(update={
                    "fallback_reason": "unknown_source",
                    "llm_latency_ms": elapsed,
                })
            if answer.confidence < 0.65:
                return decision.model_copy(update={
                    "fallback_reason": "low_confidence",
                    "llm_latency_ms": elapsed,
                })
            if answer.needs_operator != (decision.action == DecisionAction.ESCALATE):
                return decision.model_copy(update={
                    "fallback_reason": "action_mismatch",
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
                "source_ids": answer.source_ids,
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
        if len(context.asked_facts) >= limit:
            return None
        for question in playbook.questions:
            if question.fact not in context.known_facts and question.fact not in context.asked_facts:
                return question
        return None

    @staticmethod
    def next_step(playbook: Playbook, context: ConversationContext) -> Step | None:
        done = {record.step_id for record in context.completed_steps}
        facts = context.known_facts
        for step in playbook.steps:
            if step.id in done:
                continue
            if any(facts.get(key) not in values for key, values in step.when.items()):
                continue
            if any(facts.get(key) in values for key, values in step.unless.items()):
                continue
            return step
        return None

    # --- escalation ---------------------------------------------------------

    def build_escalation_card(self, context: ConversationContext, reason: str = "") -> EscalationCard:
        playbook = self.kb.get(context.playbook_id)
        request = context.original_request or _first_user_message(context)
        analysis = self._rules_analysis(request, context) if request.strip() else None
        urgency = analysis.urgency if analysis else playbook.default_urgency
        card = EscalationCard(
            original_request=request,
            summary=analysis.summary if analysis else playbook.title,
            service=analysis.service if analysis else playbook.service,
            urgency=rules.max_urgency(urgency, context.urgency or urgency),
            urgency_reason=analysis.urgency_reason if analysis else "",
            known_facts=dict(context.known_facts),
            questions_and_answers=self._questions_and_answers(playbook, context),
            performed_steps=self._performed_steps(playbook, context),
            current_result=self._current_result(playbook, context),
            escalation_reason=reason or "автоматическое решение не помогло",
            recommended_team=playbook.escalation_team,
            ai_summary="",
        )
        ai_summary, source = self._ai_summary(card)
        return card.model_copy(update={"ai_summary": ai_summary, "source": source})

    # --- internals ----------------------------------------------------------

    def _rules_analysis(self, message: str, ctx: ConversationContext) -> Analysis:
        original = ctx.original_request.strip()
        text = message if not original or original == message.strip() else f"{original} {message}"
        classification = rules.classify(text, self.kb.playbooks)
        keep_playbook = ctx.playbook_id and self.kb.has(ctx.playbook_id)
        playbook = self.kb.get(ctx.playbook_id if keep_playbook else classification.playbook_id)
        urgency, reason = rules.detect_urgency(text, playbook)
        service = rules.detect_service(text, playbook)
        symptoms = rules.detect_symptoms(text, playbook)
        return Analysis(
            summary=_summary(playbook, service, symptoms),
            service=service,
            symptoms=symptoms,
            urgency=urgency,
            urgency_reason=reason,
            known_facts={**rules.extract_facts(text), **ctx.known_facts},
            confidence=classification.confidence,
            recommended_playbook=playbook.id,
            source="rules",
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
        missing = [q.fact for q in playbook.questions if q.fact not in analysis.known_facts]
        question = self.next_question(playbook, flow_ctx)
        return analysis.model_copy(update={
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
        return next((q for q in self.kb.get(ctx.playbook_id).questions if q.fact == fact), None)

    @staticmethod
    def _escalate(playbook: Playbook, reason: str) -> Decision:
        text = (f"Передаю обращение специалисту ({playbook.escalation_team}). "
                "Всё, что мы выяснили, уже в заявке — повторять ничего не придётся.")
        if playbook.safety_notice:
            text = f"{playbook.safety_notice} {text}"
        return Decision(action=DecisionAction.ESCALATE, message=text, reason=reason,
                        escalation_team=playbook.escalation_team)

    @staticmethod
    def _questions_and_answers(playbook: Playbook, ctx: ConversationContext) -> list[dict[str, str]]:
        texts = {q.fact: q.text for q in playbook.questions}
        return [
            {"question": texts.get(fact, fact), "answer": ctx.known_facts.get(fact, "нет ответа")}
            for fact in ctx.asked_facts
        ]

    @staticmethod
    def _performed_steps(playbook: Playbook, ctx: ConversationContext) -> list[dict[str, str]]:
        titles = {step.id: step.title for step in playbook.steps}
        return [
            {"step_id": r.step_id, "step": titles.get(r.step_id, r.step_id), "result": OUTCOME_LABELS[r.outcome]}
            for r in ctx.completed_steps
        ]

    @staticmethod
    def _current_result(playbook: Playbook, ctx: ConversationContext) -> str:
        if not ctx.completed_steps:
            return "Проблема не решена, шаги самостоятельного решения не выполнялись"
        last = ctx.completed_steps[-1]
        title = next((s.title for s in playbook.steps if s.id == last.step_id), last.step_id)
        verdict = "не подтверждено пользователем" if ctx.verification_failed else OUTCOME_LABELS[last.outcome]
        return (f"Проблема не решена после {len(ctx.completed_steps)} шаг(ов); "
                f"последний шаг «{title}» — {verdict}")

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


def _summary(playbook: Playbook, service: str, symptoms: list[str]) -> str:
    title = f"Недоступен сервис {service}" if playbook.id == "service_unavailable" else playbook.title
    extra = [s for s in symptoms if s.lower() not in title.lower()]
    return f"{title}: {', '.join(extra)}" if extra else title


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
    parts.append(f"Текущий результат: {card.current_result}.")
    parts.append(f"Причина передачи: {card.escalation_reason}.")
    return " ".join(parts)
