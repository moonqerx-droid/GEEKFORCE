"""Transactional adapter between the stable HTTP contract and helpflow_ai."""

import logging

from helpflow_ai.engine import ALSO_REPORTED
from helpflow_ai import AnswerKind, ConversationContext, DecisionAction, StepRecord, TriageEngine
from sqlalchemy.orm.exc import StaleDataError

from app.models.conversation import Conversation, Message, TroubleshootingStep, utc_now
from app.core.config import get_settings
from app.repositories.conversations import ConversationRepository
from app.repositories.incidents import IncidentRepository
from app.schemas.conversation import StepOutcome
from app.services.dialogue import DialogueConflict, DialogueService
from app.services.incidents import IncidentService
from app.services.company_knowledge import company_knowledge_chunks


logger = logging.getLogger(__name__)


class TriageDialogueService(DialogueService):
    SMALLTALK_REPLIES = {
        "greeting": (
            "Привет! Я помогу разобраться с технической проблемой. "
            "Опишите, пожалуйста, что не работает или какое сообщение об ошибке вы видите."
        ),
        "help": (
            "Я могу уточнить симптомы, предложить безопасные шаги проверки и, если они не помогут, "
            "передать обращение специалисту вместе с собранным контекстом. Просто опишите проблему своими словами."
        ),
        "thanks": "Пожалуйста! Если проблема ещё не решена, продолжим с предыдущего вопроса.",
    }

    def __init__(
        self,
        repository: ConversationRepository,
        engine: TriageEngine,
        incident_service: IncidentService | None = None,
    ):
        self.repository = repository
        self.engine = engine
        self.engine.set_company_fragments([
            chunk.as_retrieved_fragment()
            for chunk in company_knowledge_chunks(repository.session)
        ])
        settings = get_settings()
        self.incident_service = incident_service or IncidentService(
            IncidentRepository(repository.session),
            threshold=settings.incident_similarity_threshold,
            min_cluster_size=settings.incident_min_cluster_size,
            window_minutes=settings.incident_window_minutes,
        )

    def create_conversation(self):
        conversation = Conversation(workflow_version="triage-v1")
        return self.repository.save(conversation)

    def get_conversation(self, conversation_id):
        conversation = super().get_conversation(conversation_id)
        conversation.answer_kind = self._answer_kind(conversation)
        conversation.citations = [
            citation.model_dump(mode="json")
            for citation in self.engine.citations_for(conversation.rag_source_ids)
        ]
        return conversation

    @staticmethod
    def _answer_kind(conversation):
        if conversation.status in {"ESCALATED", "IN_PROGRESS"}:
            return "handoff"
        codes = [conversation.current_step_code, *[step.code for step in conversation.steps]]
        if any(code and code.startswith("general.") for code in codes):
            return "general"
        if any(source_id.startswith("document:") for source_id in conversation.rag_source_ids):
            return "document"
        if conversation.playbook_id and any(message.role == "assistant" for message in conversation.messages):
            return "playbook"
        return None

    def _context(self, conversation):
        return ConversationContext(
            # A screenshot sent without words is not the request: skip empty messages.
            original_request=next((m.content for m in conversation.messages if (
                m.role == "user" and m.content.strip() and self.engine.conversation_intent(m.content) not in {
                    "greeting", "help", "thanks",
                }
            )), ""),
            messages=[{"role": m.role, "content": m.content} for m in conversation.messages],
            known_facts=conversation.known_facts,
            asked_facts=conversation.asked_facts,
            completed_steps=[StepRecord(
                step_id=s.code,
                outcome="cannot_do" if s.outcome == "cannot_perform" else s.outcome,
            ) for s in conversation.steps],
            playbook_id=conversation.playbook_id,
            urgency="medium" if conversation.urgency == "normal" else conversation.urgency,
            verification_failed=conversation.verification_failed,
        )

    ATTACHMENT_ONLY_REPLY = (
        "Файл получил, спасибо. Напишите в двух словах, что на нём или что не работает — "
        "так я быстрее разберусь."
    )

    def _message(self, conversation, role, content, *, answer_kind=None, citations=None):
        message = Message(
            role=role,
            content=content,
            answer_kind=answer_kind,
            citations=list(citations or []) if role == "assistant" else None,
        )
        if role == "user" and getattr(self, "_pending_attachments", None):
            # Files arrive with the employee's message in the same turn and transaction.
            message.attachments.extend(self._pending_attachments)
            self._pending_attachments = []
        conversation.messages.append(message)
        return message

    def _commit(self, conversation):
        # Touch the parent even when only a message/step changed, so the ORM
        # checks the version before committing this entire turn.
        conversation.updated_at = utc_now()
        try:
            self.repository.session.commit()
        except StaleDataError as exc:
            self.repository.session.rollback()
            raise DialogueConflict("conversation changed; reload it before retrying") from exc
        return self.get_conversation(conversation.id)

    def handle_message(self, conversation_id, content, *, expected_revision=None, attachments=()):
        conversation = self.get_conversation(conversation_id)
        self._check_revision(conversation, expected_revision)
        self._pending_attachments = list(attachments)
        if not content.strip() and self._pending_attachments:
            return self._attachment_only(conversation)
        if conversation.status in {"ESCALATED", "IN_PROGRESS"}:
            # A specialist owns the conversation now: keep the employee's words for them.
            try:
                self._message(conversation, "user", content.strip())
                return self._commit(conversation)
            except Exception:
                self.repository.session.rollback()
                raise
        intent = self.engine.conversation_intent(content)
        if intent == "operator":
            if conversation.status == "RESOLVED":
                raise DialogueConflict("resolved conversation cannot be escalated")
            try:
                self._message(conversation, "user", content.strip())
                self._escalate(conversation, "пользователь запросил специалиста")
                return self._commit(conversation)
            except Exception:
                self.repository.session.rollback()
                raise
        if conversation.status not in {"NEW", "CLARIFYING", "VERIFYING"}:
            raise DialogueConflict(f"messages are not accepted while status is {conversation.status}")
        try:
            previous_status = conversation.status
            self._message(conversation, "user", content.strip())
            if intent in self.SMALLTALK_REPLIES:
                self._message(conversation, "assistant", self.SMALLTALK_REPLIES[intent])
                return self._commit(conversation)
            # Recheck new information locally, without an extra LLM request.
            # The original playbook must not hide a later security/mass incident.
            if previous_status != "NEW":
                update = TriageEngine(self.engine.kb, semantic=self.engine.semantic).analyze(content)
                if update.should_escalate:
                    conversation.playbook_id = update.recommended_playbook
                    conversation.urgency = "critical"
                    conversation.urgency_reason = update.urgency_reason
                    conversation.summary = update.summary
                    conversation.known_facts = {
                        **conversation.known_facts, **update.known_facts,
                        "critical_update": content.strip(),
                    }
                    self._escalate(conversation, "в ходе диалога выявлен критический инцидент")
                    return self._commit(conversation)
            if previous_status == "NEW":
                analysis = self.engine.analyze(content)
                for field in ("summary", "service", "symptoms", "urgency_reason", "known_facts", "missing_facts", "confidence"):
                    setattr(conversation, field, getattr(analysis, field))
                conversation.urgency = "normal" if analysis.urgency.value == "medium" else analysis.urgency.value
                conversation.playbook_id = analysis.recommended_playbook
                match = None
                try:
                    with self.repository.session.begin_nested():
                        match = self.incident_service.match_first_turn(conversation.id)
                except Exception as error:
                    logger.exception(
                        "incident.detection_failed conversation_id=%s error=%s",
                        conversation.id,
                        type(error).__name__,
                    )
                if match is not None:
                    conversation.incident_id = match.incident_id
                    conversation.status = "ESCALATED"
                    conversation.escalated_at = conversation.escalated_at or utc_now()
                    conversation.current_step_code = None
                    conversation.current_step_instruction = None
                    card = self.engine.build_escalation_card(
                        self._context(conversation),
                        "обращение совпало с возможным массовым инцидентом",
                    )
                    conversation.escalation_card = card.model_dump(mode="json")
                    conversation.escalation_summary = card.ai_summary
                    self._message(
                        conversation,
                        "assistant",
                        self._outage_notice(conversation, match),
                        answer_kind="handoff",
                    )
                    return self._commit(conversation)
                if analysis.should_escalate:
                    self._escalate(conversation, "сценарий требует немедленного участия специалиста")
                else:
                    self._advance(conversation)
            elif previous_status == "CLARIFYING":
                context = self._context(conversation)
                added = self.engine.reports_new_problem(content, context)
                if added is not None:
                    # Not an answer but one more problem: keep it and say so instead of
                    # filing «а ещё интернет пропал» as the error text.
                    earlier = conversation.known_facts.get(ALSO_REPORTED)
                    conversation.known_facts = {
                        **conversation.known_facts,
                        ALSO_REPORTED: f"{earlier}; {content.strip()}" if earlier else content.strip(),
                    }
                    title = self.engine.kb.get(added).title
                    if self.engine.is_root_cause(added):
                        # Without the internet the mail questions are pointless: switch to it;
                        # the earlier problem stays in the plan and comes next.
                        playbook = self.engine.kb.get(added)
                        conversation.playbook_id = added
                        conversation.service = playbook.service
                        conversation.summary = f"{playbook.title}. Ещё: {conversation.summary}"
                        intro = f"Записал и это: «{title}». Начнём с этого — от него часто зависит и остальное."
                    else:
                        intro = f"Записал и это: «{title}» — займёмся, когда закончим с текущей проблемой."
                    self._advance(conversation, intro=intro)
                    return self._commit(conversation)
                facts = self.engine.absorb_answer(content, context)
                conversation.known_facts = {**conversation.known_facts, **facts}
                picked = facts.get("problem_area")
                if (conversation.playbook_id == "unknown" and update.recommended_playbook == "unknown"
                        and picked not in (None, "other", "unknown") and self.engine.kb.has(picked)):
                    # A tap on «Почта» is an explicit choice, not something to guess from keywords.
                    update = update.model_copy(update={
                        "recommended_playbook": picked,
                        "service": self.engine.kb.get(picked).service,
                        "summary": self.engine.kb.get(picked).title,
                    })
                if conversation.playbook_id == "unknown" and update.recommended_playbook != "unknown":
                    conversation.playbook_id = update.recommended_playbook
                    conversation.summary = update.summary
                    conversation.service = update.service
                    conversation.symptoms = update.symptoms
                    conversation.confidence = update.confidence
                    conversation.known_facts = {**conversation.known_facts, **update.known_facts}
                    levels = ["low", "normal", "high", "critical"]
                    urgency = "normal" if update.urgency.value == "medium" else update.urgency.value
                    if levels.index(urgency) >= levels.index(conversation.urgency):
                        conversation.urgency = urgency
                        conversation.urgency_reason = update.urgency_reason
                self._advance(conversation)
            else:
                solved = self.engine.interpret_confirmation(content)
                if solved is True:
                    conversation.status = "RESOLVED"
                    conversation.resolved_at = utc_now()
                    conversation.resolved_by = "assistant"
                    self._message(conversation, "assistant", "Отлично, проблема решена. Обращение закрыто.")
                elif solved is False:
                    conversation.verification_failed = True
                    self._advance(conversation)
                else:
                    self._message(conversation, "assistant", "Подтвердите, пожалуйста, явно: проблема решена — да или нет?")
            return self._commit(conversation)
        except Exception:
            self.repository.session.rollback()
            raise

    def _attachment_only(self, conversation):
        """A screenshot with no words: keep it and ask for a short description, change nothing else."""
        if conversation.status == "RESOLVED":
            raise DialogueConflict("resolved conversation cannot accept files")
        try:
            self._message(conversation, "user", "")
            if conversation.status not in {"ESCALATED", "IN_PROGRESS"}:
                self._message(conversation, "assistant", self.ATTACHMENT_ONLY_REPLY)
            return self._commit(conversation)
        except Exception:
            self.repository.session.rollback()
            raise

    def quick_replies(self, conversation) -> list[str]:
        """One-tap answers while the assistant waits for a reply to a closed question."""
        if conversation.status != "CLARIFYING" or not conversation.asked_facts:
            return []
        fact = conversation.asked_facts[-1]
        if fact in conversation.known_facts:
            return []
        return self.engine.quick_replies(conversation.playbook_id, fact)

    def record_step_result(self, conversation_id, outcome, *, expected_revision=None, step_code=None):
        conversation = self.get_conversation(conversation_id)
        self._check_revision(conversation, expected_revision)
        if step_code is not None and step_code != conversation.current_step_code:
            raise DialogueConflict("active step changed; reload the conversation")
        if conversation.status != "TROUBLESHOOTING" or not conversation.current_step_code:
            raise DialogueConflict("step result requires an active TROUBLESHOOTING step")
        parsed = StepOutcome(outcome)
        try:
            conversation.steps.append(TroubleshootingStep(
                code=conversation.current_step_code,
                instruction=conversation.current_step_instruction,
                outcome=parsed.value,
                position=len(conversation.steps),
            ))
            conversation.verification_failed = False
            if conversation.answer_kind == "document" and parsed == StepOutcome.HELPED:
                # «Да, это ответ» on a company-document answer already is the confirmation;
                # asking «решило ли это вопрос?» again would only make the employee click twice.
                conversation.current_step_code = None
                conversation.current_step_instruction = None
                conversation.status = "RESOLVED"
                conversation.resolved_at = utc_now()
                conversation.resolved_by = "assistant"
                self._message(conversation, "assistant", "Отлично, ответ нашёлся. Обращение закрыто — если появится новый вопрос, просто напишите.")
                return self._commit(conversation)
            self._advance(conversation)
            return self._commit(conversation)
        except Exception:
            self.repository.session.rollback()
            raise

    def _advance(self, conversation, intro: str = ""):
        decision = self.engine.decide(self._context(conversation))
        conversation.rag_source_ids = list(decision.source_ids)
        conversation.ai_fallback_reason = decision.fallback_reason
        conversation.ai_latency_ms = decision.llm_latency_ms
        conversation.answer_kind = decision.answer_kind.value if decision.answer_kind else None
        conversation.citations = [citation.model_dump(mode="json") for citation in decision.citations]
        conversation.current_step_code = None
        conversation.current_step_instruction = None
        playbook = self.engine.kb.get(conversation.playbook_id)
        conversation.missing_facts = [q.fact for q in playbook.questions if q.fact not in conversation.known_facts]
        if decision.action == DecisionAction.ESCALATE:
            # The engine explains the hand-off in its own words (what it already noted, who takes it).
            self._escalate(conversation, decision.reason, message=decision.message)
            return
        if decision.action == DecisionAction.ASK:
            conversation.status = "CLARIFYING"
            conversation.asked_facts = [*conversation.asked_facts, decision.question.fact]
        elif decision.action == DecisionAction.STEP:
            conversation.status = "TROUBLESHOOTING"
            conversation.current_step_code = decision.step.id
            conversation.current_step_instruction = decision.message
        else:
            conversation.status = "VERIFYING"
        if decision.answer_kind == AnswerKind.DOCUMENT and decision.citations and not conversation.steps:
            # A question about the rules is not a «Проблема со входом»: name what was asked about.
            document = decision.citations[0].title.split(" — ")[0]
            conversation.summary = f"Вопрос по документу «{document}»"
        self._message(
            conversation,
            "assistant",
            f"{intro} {decision.message}" if intro else decision.message,
            answer_kind=decision.answer_kind.value if decision.answer_kind else None,
            citations=[citation.model_dump(mode="json") for citation in decision.citations],
        )

    def _escalate(self, conversation, reason, message=None):
        card = self.engine.build_escalation_card(self._context(conversation), reason)
        conversation.status = "ESCALATED"
        conversation.escalated_at = conversation.escalated_at or utc_now()
        conversation.current_step_code = None
        conversation.current_step_instruction = None
        conversation.escalation_card = card.model_dump(mode="json")
        conversation.escalation_summary = card.ai_summary
        playbook = self.engine.kb.get(conversation.playbook_id)
        message = message or f"Обращение передано специалисту ({card.recommended_team}) вместе с собранным контекстом."
        if playbook.safety_notice and playbook.safety_notice not in message:
            message = f"{playbook.safety_notice} {message}"
        conversation.answer_kind = "handoff"
        conversation.citations = []
        self._message(conversation, "assistant", message, answer_kind="handoff")
        try:
            with self.repository.session.begin_nested():
                self.incident_service.observe_escalated(conversation.id)
                self.repository.session.flush()
        except Exception as error:
            logger.exception(
                "incident.detection_failed conversation_id=%s error=%s",
                conversation.id,
                type(error).__name__,
            )

    def _outage_notice(self, conversation, match) -> str:
        service = conversation.service or "сервис"
        text = (f"Похоже, это общий сбой: {service} не работает у нескольких коллег, "
                "специалисты уже чинят. Проверять что-то у себя не нужно: новости придут сюда, в этот чат.")
        latest = self.incident_service.latest_update_text(match.incident_id)
        return f"{text} Последнее обновление: {latest}" if latest else text

    def escalate(self, conversation_id):
        conversation = self.get_conversation(conversation_id)
        if conversation.status == "RESOLVED":
            raise DialogueConflict("resolved conversation cannot be escalated")
        if conversation.status in {"ESCALATED", "IN_PROGRESS"}:
            return conversation
        try:
            self._escalate(conversation, "пользователь запросил специалиста")
            return self._commit(conversation)
        except Exception:
            self.repository.session.rollback()
            raise
