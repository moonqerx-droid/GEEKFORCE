"""Transactional adapter between the stable HTTP contract and helpflow_ai."""

import logging
from datetime import timedelta

from app.services import ocr
from helpflow_ai import rules, voice
from helpflow_ai.engine import ALSO_REPORTED, CURRENT_QUESTION
from helpflow_ai import AnswerKind, ConversationContext, DecisionAction, StepRecord, TriageEngine
from sqlalchemy import select, update
from sqlalchemy.orm.exc import StaleDataError

from app.models.attachment import Attachment
from app.models.conversation import Conversation, Message, TroubleshootingStep, utc_now
from app.core.config import get_settings
from app.repositories.conversations import ConversationRepository
from app.repositories.incidents import IncidentRepository
from app.schemas.conversation import StepOutcome
from app.services.dialogue import DialogueConflict, DialogueService
from app.services.incidents import IncidentService
from app.services import learning
from app.services.company_knowledge import company_knowledge_chunks
from app.services.sla import TARGET_MINUTES


logger = logging.getLogger(__name__)


class TriageDialogueService(DialogueService):
    SMALLTALK_REPLIES = {
        "greeting": (
            "Привет! Я помогу разобраться с технической проблемой. "
            "Опишите, пожалуйста, что не работает или какое сообщение об ошибке вы видите."
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
        # What helped colleagues, approved by the support lead: offered before a hand-off.
        self.engine.set_learned_steps(learning.engine_items(repository.session))
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
            )), "") or conversation.known_facts.get(self.SCREENSHOT_FACT, ""),
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
        "Файл получен, спасибо. Напишите в двух словах, что на нём или что не работает — "
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
        typed = content.strip()
        seen = self._read_screenshots(conversation, self._pending_attachments)
        if seen:
            # The engine reads the words and the screenshot; history keeps what was typed.
            content = f"{typed}. {seen}" if typed else seen
        if not content.strip() and self._pending_attachments:
            return self._attachment_only(conversation)
        self._raise_urgency(conversation, content)
        if conversation.status in {"ESCALATED", "IN_PROGRESS"}:
            # A specialist owns the conversation now: keep the employee's words for them.
            try:
                self._message(conversation, "user", typed)
                return self._commit(conversation)
            except Exception:
                self.repository.session.rollback()
                raise
        intent = self.engine.conversation_intent(content)
        if intent == "operator":
            if conversation.status == "RESOLVED":
                raise DialogueConflict("resolved conversation cannot be escalated")
            try:
                self._message(conversation, "user", typed)
                self._escalate(conversation, "пользователь запросил специалиста")
                return self._commit(conversation)
            except Exception:
                self.repository.session.rollback()
                raise
        if intent == "help" and conversation.status in {"NEW", "CLARIFYING", "VERIFYING", "TROUBLESHOOTING"}:
            # «Что ты умеешь?» at any point: the list, and the conversation stays where it was.
            try:
                self._message(conversation, "user", typed)
                self._message(conversation, "assistant", self.engine.capabilities())
                return self._commit(conversation)
            except Exception:
                self.repository.session.rollback()
                raise
        if conversation.status == "TROUBLESHOOTING":
            return self._typed_during_step(conversation, content, typed)
        if conversation.status not in {"NEW", "CLARIFYING", "VERIFYING"}:
            raise DialogueConflict(f"messages are not accepted while status is {conversation.status}")
        try:
            previous_status = conversation.status
            self._message(conversation, "user", typed)
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
                self._merge_screenshot_facts(conversation)
                conversation.urgency = "normal" if analysis.urgency.value == "medium" else analysis.urgency.value
                conversation.playbook_id = analysis.recommended_playbook
                match = None
                try:
                    # A question («раз в сколько дней меняем пароль?») is not a report of an outage.
                    if not self.engine.answer_policy.is_information_question(content):
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
                    # One human sentence for «задолбали!!!» or «опять», then straight to business.
                    self._advance(conversation, intro=voice.acknowledgement(typed))
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
                    solved = self.engine.problem_count(self._context(conversation))
                    text = ("Отлично, обе проблемы решены. Обращение закрыто." if solved == 2 else
                            "Отлично, все проблемы из обращения решены. Обращение закрыто." if solved > 2 else
                            "Отлично, проблема решена. Обращение закрыто.")
                    self._message(conversation, "assistant", text)
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

    OPEN_STATUSES = ("CLARIFYING", "TROUBLESHOOTING", "VERIFYING", "ESCALATED", "IN_PROGRESS")
    SIMILAR_WINDOW = timedelta(days=3)

    def similar_open(self, conversation):
        """The employee's other open request about the same problem, while this one is fresh:
        continuing there beats explaining everything again."""
        if (not conversation.owner_id or conversation.playbook_id in (None, "unknown")
                or conversation.status not in self.OPEN_STATUSES
                or sum(m.role == "user" for m in conversation.messages) > 2):
            return None
        return self.repository.session.scalar(
            select(Conversation)
            .where(
                Conversation.owner_id == conversation.owner_id,
                Conversation.id != conversation.id,
                Conversation.playbook_id == conversation.playbook_id,
                Conversation.status.in_(self.OPEN_STATUSES),
                Conversation.created_at >= utc_now() - self.SIMILAR_WINDOW,
                Conversation.created_at < conversation.created_at,
            )
            .order_by(Conversation.created_at.desc())
            .limit(1)
        )

    def merge_into_similar(self, conversation_id):
        """«Продолжить там»: the new request's words move to the employee's earlier open one about
        the same problem, and the duplicate disappears — nothing to explain twice, nothing left over."""
        conversation = self.get_conversation(conversation_id)
        target = self.similar_open(conversation)
        if target is None:
            raise DialogueConflict("there is no similar open conversation to continue")
        try:
            for message in sorted(conversation.messages, key=lambda item: item.id):
                if message.role != "user":
                    continue
                moved = Message(role="user", content=message.content)
                moved.attachments.extend(message.attachments)
                target.messages.append(moved)
            self.repository.session.flush()
            # Files belong to the conversation too: move them before the duplicate is deleted.
            self.repository.session.execute(
                update(Attachment).where(Attachment.conversation_id == conversation.id)
                .values(conversation_id=target.id)
            )
            target.updated_at = utc_now()
            self.repository.session.flush()
            self.repository.session.delete(conversation)
            self.repository.session.commit()
        except Exception:
            self.repository.session.rollback()
            raise
        return self.get_conversation(target.id)

    def quick_replies(self, conversation) -> list[str]:
        """One-tap answers while the assistant waits for a reply to a closed question."""
        if conversation.status != "CLARIFYING" or not conversation.asked_facts:
            return []
        fact = conversation.asked_facts[-1]
        if fact in conversation.known_facts:
            return []
        return self.engine.quick_replies(conversation.playbook_id, fact)

    def question_reason(self, conversation) -> str | None:
        """Why the question on screen is asked: its answer decides the next step."""
        if conversation.status != "CLARIFYING" or not conversation.asked_facts:
            return None
        fact = conversation.asked_facts[-1]
        if fact in conversation.known_facts:
            return None
        playbook = self.engine.kb.get(conversation.playbook_id)
        return next((question.why for question in playbook.questions if question.fact == fact), None)

    STEP_TEXT_UNCLEAR = (
        "Не удалось понять, как прошёл шаг. Напишите «помогло» или «не помогло» — или нажмите кнопку "
        "под шагом. Если выполнить его не получается, так и напишите: предложу другой путь."
    )

    def _typed_during_step(self, conversation, content, typed=None):
        """A message typed while a step is on screen: its result, one more problem, or neither."""
        if conversation.answer_kind == "document":
            # «а за рубежом?» after a document answer is the next question, not a step result.
            context = self._context(conversation)
            follow_up = self.engine.answer_follow_up(
                content, context.known_facts.get(CURRENT_QUESTION) or context.original_request)
            if follow_up is not None:
                try:
                    self._message(conversation, "user", content.strip() if typed is None else typed)
                    conversation.known_facts = {**conversation.known_facts, CURRENT_QUESTION: content.strip()}
                    self._advance(conversation, decision=follow_up)
                    return self._commit(conversation)
                except Exception:
                    self.repository.session.rollback()
                    raise
        # Another problem first: «и ещё почта не открывается» is not «не помогло».
        added = self.engine.reports_new_problem(content, self._context(conversation))
        outcome = None if added is not None else self.engine.interpret_step_result(content)
        try:
            self._message(conversation, "user", content.strip() if typed is None else typed)
            if outcome is not None:
                self._apply_step_outcome(conversation, StepOutcome(outcome))
                return self._commit(conversation)
            if added is not None:
                earlier = conversation.known_facts.get(ALSO_REPORTED)
                conversation.known_facts = {
                    **conversation.known_facts,
                    ALSO_REPORTED: f"{earlier}; {content.strip()}" if earlier else content.strip(),
                }
                title = self.engine.kb.get(added).title
                self._message(conversation, "assistant",
                              f"Записал и это: «{title}» — займёмся следом. А текущий шаг помог?")
            else:
                self._message(conversation, "assistant", self.STEP_TEXT_UNCLEAR)
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
        try:
            self._apply_step_outcome(conversation, StepOutcome(outcome))
            return self._commit(conversation)
        except Exception:
            self.repository.session.rollback()
            raise

    def _apply_step_outcome(self, conversation, parsed):
        """Record the step's result and move on; the caller commits."""
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
            return
        self._advance(conversation)

    SCREENSHOT_FACT = "screenshot_text"

    def _read_screenshots(self, conversation, attachments) -> str | None:
        """Text of attached screenshots; also files it into the case for the specialist."""
        self._screenshot_facts, self._screenshot_intro = {}, ""
        texts = [ocr.read_text(item.data, item.content_type) for item in attachments]
        seen = "\n".join(text for text in texts if text)
        if not seen:
            return None
        line = ocr.error_line(seen)
        self._screenshot_facts = {self.SCREENSHOT_FACT: seen}
        if line:
            self._screenshot_facts["error_text"] = line
            self._screenshot_intro = f"На скриншоте вижу: «{line.rstrip('. ')}»."
        else:
            self._screenshot_intro = "Скриншот прочитан."
        self._merge_screenshot_facts(conversation)
        return seen

    def _merge_screenshot_facts(self, conversation):
        facts = getattr(self, "_screenshot_facts", None)
        if facts:
            # What the employee typed wins over what OCR read.
            conversation.known_facts = {**facts, **conversation.known_facts,
                                        self.SCREENSHOT_FACT: facts[self.SCREENSHOT_FACT]}

    def _advance(self, conversation, intro: str = "", decision=None):
        self._merge_screenshot_facts(conversation)
        seen_intro = getattr(self, "_screenshot_intro", "")
        if seen_intro:
            intro = f"{intro} {seen_intro}".strip()  # sympathy first, then what was read
            self._screenshot_intro = ""
        decision = decision or self.engine.decide(self._context(conversation))
        if decision.remember:
            # «This problem waits for a specialist», «the second problem has started»: kept with
            # the conversation, so the next turn and the hand-off card know it.
            conversation.known_facts = {**conversation.known_facts, **decision.remember}
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
            if "источника для ответа на вопрос" in (decision.reason or "") and conversation.playbook_id in (None, "unknown"):
                # A question the documents do not answer: the specialist sees a question, not «Не определён».
                conversation.service = "Вопрос о правилах компании"
                conversation.summary = self._context(conversation).original_request[:200] or conversation.summary
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
        asked = self._context(conversation).original_request
        if (decision.answer_kind == AnswerKind.DOCUMENT and decision.citations and not conversation.steps
                and ("?" in asked or self.engine.answer_policy.is_information_question(asked)
                     or self.engine.answer_policy.asks_about_rules(asked))):
            # A question about the rules is not a «Проблема со входом»: name what was asked about.
            document = decision.citations[0].title.split(" — ")[0]
            conversation.summary = f"Вопрос по документу «{document}»"
            # «Где» in the card: the document's subject, not «Не определён».
            conversation.service = f"Правила компании: {document}"
        self._message(
            conversation,
            "assistant",
            f"{intro} {decision.message}" if intro else decision.message,
            answer_kind=decision.answer_kind.value if decision.answer_kind else None,
            citations=[citation.model_dump(mode="json") for citation in decision.citations],
        )

    URGENCY_LEVELS = ("low", "normal", "high", "critical")

    def _raise_urgency(self, conversation, content):
        """Any message may make a request more urgent, never less: «срочно, дайте специалиста»
        or «через 10 минут встреча, где специалист?» moves it up the specialist's queue."""
        signal = rules.urgency_signal(content)
        if signal is None:
            return
        urgency, reason = signal
        level = "normal" if urgency.value == "medium" else urgency.value
        current = conversation.urgency or "normal"
        if self.URGENCY_LEVELS.index(level) > self.URGENCY_LEVELS.index(current):
            conversation.urgency = level
            conversation.urgency_reason = reason

    def _escalate(self, conversation, reason, message=None):
        card = self.engine.build_escalation_card(self._context(conversation), reason)
        conversation.status = "ESCALATED"
        conversation.escalated_at = conversation.escalated_at or utc_now()
        conversation.current_step_code = None
        conversation.current_step_instruction = None
        conversation.escalation_card = card.model_dump(mode="json")
        conversation.escalation_summary = card.ai_summary
        playbook = self.engine.kb.get(conversation.playbook_id)
        message = message or f"Обращение передано {voice.to_whom(card.recommended_team)} вместе с собранным контекстом."
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

    URGENT_REASON = "сотрудник отметил обращение как срочное"

    def mark_urgent(self, conversation_id):
        """«Срочно»: at once to a specialist, marked urgent, with a promise of when
        they answer. Already with a specialist: it only gets the mark and the shorter deadline."""
        conversation = self.get_conversation(conversation_id)
        if conversation.status == "RESOLVED":
            raise DialogueConflict("resolved conversation cannot be marked urgent")
        if not any(m.role == "user" and m.content.strip() for m in conversation.messages):
            raise DialogueConflict("describe the problem before marking it urgent")
        try:
            if conversation.urgency != "critical":
                conversation.urgency = "high"
                conversation.urgency_reason = self.URGENT_REASON
            promise = f"специалист ответит в течение {_within(TARGET_MINUTES[conversation.urgency])}"
            if conversation.status in {"ESCALATED", "IN_PROGRESS"}:
                card = dict(conversation.escalation_card or {})
                if card and card.get("urgency") != "critical":
                    card.update(urgency="high", urgency_reason=self.URGENT_REASON)
                    conversation.escalation_card = card
                self._message(conversation, "assistant",
                              f"Отметил как срочное — специалист видит пометку «Срочно» и срок: {promise}.",
                              answer_kind="handoff")
            else:
                team = self.engine.kb.get(conversation.playbook_id).escalation_team
                self._escalate(conversation, self.URGENT_REASON, message=(
                    f"Отметил как срочное и сразу передал {voice.to_whom(team)}: {promise}. "
                    "Всё, что мы выяснили, уже в заявке — повторять ничего не придётся."))
            return self._commit(conversation)
        except Exception:
            self.repository.session.rollback()
            raise

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


def _within(minutes: int) -> str:
    """«15 минут», «часа», «4 часов» — how soon, as it reads after «в течение»."""
    if minutes == 60:
        return "часа"
    if minutes % 60 == 0:
        return f"{minutes // 60} часов"  # «4 часов»: the genitive after «в течение»
    return f"{minutes} минут"
