from app.models.conversation import Conversation
from app.repositories.conversations import ConversationRepository
from app.schemas.conversation import ConversationStatus, StepOutcome
from app.services.ai import AIService


class DialogueConflict(RuntimeError):
    pass


class ConversationNotFound(LookupError):
    pass


class DialogueService:
    def __init__(self, repository: ConversationRepository, ai_service: AIService):
        self.repository = repository
        self.ai_service = ai_service

    def create_conversation(self) -> Conversation:
        return self.repository.create()

    def get_conversation(self, conversation_id: str) -> Conversation:
        conversation = self.repository.get(conversation_id)
        if conversation is None:
            raise ConversationNotFound(conversation_id)
        return conversation

    def handle_message(self, conversation_id: str, content: str) -> Conversation:
        conversation = self.get_conversation(conversation_id)
        if conversation.status in {ConversationStatus.RESOLVED, ConversationStatus.ESCALATED}:
            raise DialogueConflict("terminal conversation cannot accept messages")
        allowed_states = {
            ConversationStatus.NEW,
            ConversationStatus.CLARIFYING,
            ConversationStatus.VERIFYING,
        }
        if conversation.status not in allowed_states:
            raise DialogueConflict(f"messages are not accepted while status is {conversation.status}")

        self.repository.add_message(conversation_id, role="user", content=content.strip())

        if conversation.status == ConversationStatus.NEW:
            return self._analyze_initial_message(conversation, content)
        if conversation.status == ConversationStatus.CLARIFYING:
            return self._start_troubleshooting(conversation, content)
        if conversation.status == ConversationStatus.VERIFYING:
            return self._verify_resolution(conversation, content)

        raise DialogueConflict(f"unsupported conversation state {conversation.status}")

    def record_step_result(self, conversation_id: str, outcome: str) -> Conversation:
        conversation = self.get_conversation(conversation_id)
        if conversation.status != ConversationStatus.TROUBLESHOOTING:
            raise DialogueConflict("step result requires TROUBLESHOOTING state")
        if not conversation.current_step_code or not conversation.current_step_instruction:
            raise DialogueConflict("conversation has no active step")

        parsed_outcome = StepOutcome(outcome)
        self.repository.add_step_result(
            conversation_id,
            code=conversation.current_step_code,
            instruction=conversation.current_step_instruction,
            outcome=parsed_outcome.value,
        )

        if parsed_outcome == StepOutcome.HELPED:
            conversation.status = ConversationStatus.VERIFYING
            conversation.current_step_code = None
            conversation.current_step_instruction = None
            assistant_text = "Проверьте ещё раз: нужная функция теперь работает?"
        else:
            next_steps = {
                "check_vpn": (
                    "try_private_window",
                    "Откройте CRM в приватном окне браузера и попробуйте войти снова.",
                ),
                "try_private_window": (
                    "clear_site_data",
                    "Очистите данные сайта CRM и повторите вход.",
                ),
            }
            next_step = next_steps.get(conversation.current_step_code)
            if next_step is None:
                return self.escalate(conversation_id)
            conversation.current_step_code, conversation.current_step_instruction = next_step
            assistant_text = conversation.current_step_instruction

        saved = self.repository.save(conversation)
        self.repository.add_message(conversation_id, role="assistant", content=assistant_text)
        return self.get_conversation(saved.id)

    def escalate(self, conversation_id: str) -> Conversation:
        conversation = self.get_conversation(conversation_id)
        if conversation.status == ConversationStatus.RESOLVED:
            raise DialogueConflict("resolved conversation cannot be escalated")
        if conversation.status == ConversationStatus.ESCALATED:
            return conversation

        conversation.status = ConversationStatus.ESCALATED
        conversation.current_step_code = None
        conversation.current_step_instruction = None
        conversation.escalation_summary = self._build_escalation_summary(conversation)
        self.repository.save(conversation)
        self.repository.add_message(
            conversation_id,
            role="assistant",
            content="Обращение передано специалисту вместе с собранным контекстом.",
        )
        return self.get_conversation(conversation_id)

    def _analyze_initial_message(self, conversation: Conversation, content: str) -> Conversation:
        conversation.status = ConversationStatus.ANALYZING
        analysis = self.ai_service.analyze(content)
        conversation.summary = analysis.summary
        conversation.service = analysis.service
        conversation.symptoms = analysis.symptoms
        conversation.urgency = analysis.urgency
        conversation.urgency_reason = analysis.urgency_reason
        conversation.known_facts = analysis.known_facts
        conversation.missing_facts = analysis.missing_facts
        conversation.confidence = analysis.confidence
        conversation.playbook_id = analysis.recommended_playbook
        conversation.status = ConversationStatus.CLARIFYING
        self.repository.save(conversation)
        self.repository.add_message(
            conversation.id,
            role="assistant",
            content=analysis.next_question,
        )
        return self.get_conversation(conversation.id)

    def _start_troubleshooting(self, conversation: Conversation, content: str) -> Conversation:
        facts = dict(conversation.known_facts)
        facts["error_description"] = content.strip()
        conversation.known_facts = facts
        conversation.missing_facts = []
        if conversation.playbook_id != "crm_login_device_specific":
            self.repository.save(conversation)
            return self.escalate(conversation.id)
        conversation.status = ConversationStatus.TROUBLESHOOTING
        conversation.current_step_code = "check_vpn"
        conversation.current_step_instruction = "Проверьте, что корпоративный VPN подключён, затем повторите вход в CRM."
        self.repository.save(conversation)
        self.repository.add_message(
            conversation.id,
            role="assistant",
            content=conversation.current_step_instruction,
        )
        return self.get_conversation(conversation.id)

    def _verify_resolution(self, conversation: Conversation, content: str) -> Conversation:
        lowered = content.casefold()
        negative_markers = ("нет", "не работает", "не помог", "ошибка осталась", "не восстанов")
        affirmative_markers = ("да", "работает", "восстанов", "получилось", "помогло")
        if any(marker in content.casefold() for marker in negative_markers):
            conversation.status = ConversationStatus.TROUBLESHOOTING
            conversation.current_step_code = "clear_site_data"
            conversation.current_step_instruction = "Очистите данные сайта CRM и повторите вход."
            assistant_text = conversation.current_step_instruction
        elif any(marker in lowered for marker in affirmative_markers):
            conversation.status = ConversationStatus.RESOLVED
            assistant_text = "Отлично, проблема решена. Обращение закрыто."
        else:
            conversation.status = ConversationStatus.VERIFYING
            assistant_text = "Подтвердите, пожалуйста, явно: проблема решена — да или нет?"
        self.repository.save(conversation)
        self.repository.add_message(conversation.id, role="assistant", content=assistant_text)
        return self.get_conversation(conversation.id)

    @staticmethod
    def _build_escalation_summary(conversation: Conversation) -> str:
        steps = "; ".join(f"{step.instruction} — {step.outcome}" for step in conversation.steps)
        original_request = next(
            (message.content for message in conversation.messages if message.role == "user"),
            "не сохранено",
        )
        dialogue = " | ".join(
            f"{message.role}: {message.content}" for message in conversation.messages
        )
        return (
            f"Сервис: {conversation.service or 'не определён'}. "
            f"Срочность: {conversation.urgency}. "
            f"Причина срочности: {conversation.urgency_reason or 'не указана'}. "
            f"Проблема: {conversation.summary or 'не определена'}. "
            f"Исходное обращение: {original_request}. "
            f"Факты: {conversation.known_facts}. "
            f"Диалог: {dialogue or 'нет'}. "
            f"Выполненные шаги: {steps or 'нет'}."
        )
