from typing import Protocol

from pydantic import BaseModel

from app.schemas.conversation import Urgency


class AIAnalysis(BaseModel):
    summary: str
    service: str
    symptoms: list[str]
    urgency: Urgency
    urgency_reason: str | None
    known_facts: dict[str, str]
    missing_facts: list[str]
    next_question: str
    confidence: float
    recommended_playbook: str
    should_escalate: bool = False


class AIService(Protocol):
    def analyze(self, message: str) -> AIAnalysis: ...


class MockAIService:
    """Predictable offline implementation for development and demos."""

    def analyze(self, message: str) -> AIAnalysis:
        normalized = message.strip()
        if not normalized:
            raise ValueError("message must not be blank")

        lowered = normalized.casefold()
        is_crm = "crm" in lowered or "срм" in lowered
        is_urgent = any(marker in lowered for marker in ("через 20", "срочно", "встреч"))

        if is_crm:
            symptoms = ["не удаётся войти в CRM"]
            if "ноутбук" in lowered or "ноутбука" in lowered:
                symptoms.append("проблема проявляется на ноутбуке")
            return AIAnalysis(
                summary="Пользователь не может войти в CRM",
                service="CRM",
                symptoms=symptoms,
                urgency=Urgency.HIGH if is_urgent else Urgency.NORMAL,
                urgency_reason="Важная встреча в ближайшие 20 минут" if is_urgent else None,
                known_facts={"device": "ноутбук"} if "ноутбук" in lowered else {},
                missing_facts=["текст ошибки"],
                next_question="Какое сообщение или код ошибки появляется при входе?",
                confidence=0.9,
                recommended_playbook="crm_login_device_specific",
            )

        return AIAnalysis(
            summary="Недостаточно данных для определения проблемы",
            service="Не определён",
            symptoms=[],
            urgency=Urgency.HIGH if is_urgent else Urgency.NORMAL,
            urgency_reason="Пользователь отметил срочность" if is_urgent else None,
            known_facts={},
            missing_facts=["затронутый сервис", "наблюдаемый симптом"],
            next_question="Какой сервис не работает и что именно вы видите на экране?",
            confidence=0.25,
            recommended_playbook="generic_clarification",
        )

