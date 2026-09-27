"""Transactional adapter between the stable HTTP contract and helpflow_ai."""

from helpflow_ai import ConversationContext, DecisionAction, StepRecord, TriageEngine
from sqlalchemy.orm.exc import StaleDataError

from app.models.conversation import Conversation, Message, TroubleshootingStep, utc_now
from app.repositories.conversations import ConversationRepository
from app.schemas.conversation import StepOutcome
from app.services.dialogue import DialogueConflict, DialogueService


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

    def __init__(self, repository: ConversationRepository, engine: TriageEngine):
        self.repository = repository
        self.engine = engine

    def create_conversation(self):
        conversation = Conversation(workflow_version="triage-v1")
        return self.repository.save(conversation)

    def _context(self, conversation):
        return ConversationContext(
            original_request=next((m.content for m in conversation.messages if (
                m.role == "user" and self.engine.conversation_intent(m.content) not in {
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

    @staticmethod
    def _message(conversation, role, content):
        conversation.messages.append(Message(role=role, content=content))

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

    def handle_message(self, conversation_id, content, *, expected_revision=None):
        conversation = self.get_conversation(conversation_id)
        self._check_revision(conversation, expected_revision)
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
                update = TriageEngine(self.engine.kb).analyze(content)
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
                if analysis.should_escalate:
                    self._escalate(conversation, "сценарий требует немедленного участия специалиста")
                else:
                    self._advance(conversation)
            elif previous_status == "CLARIFYING":
                facts = self.engine.absorb_answer(content, self._context(conversation))
                conversation.known_facts = {**conversation.known_facts, **facts}
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
            self._advance(conversation)
            return self._commit(conversation)
        except Exception:
            self.repository.session.rollback()
            raise

    def _advance(self, conversation):
        decision = self.engine.decide(self._context(conversation))
        conversation.rag_source_ids = list(decision.source_ids)
        conversation.ai_fallback_reason = decision.fallback_reason
        conversation.ai_latency_ms = decision.llm_latency_ms
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
        self._message(conversation, "assistant", decision.message)

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
        self._message(conversation, "assistant", message)

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
