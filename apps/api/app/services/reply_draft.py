"""A first reply for the specialist, written from the assistant's card: they edit it and send.

No model is needed: everything the reply says is already known — who wrote, what happened, what
they tried, how urgent it is and what helped colleagues with the same problem last time.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.auth import User
from app.models.conversation import Conversation, Message

RESOLUTION_PREFIX = "Обращение закрыто. Итог: "
_ENGINE_REASONS = frozenset({
    "пользователь отмечает срочность", "работа сотрудника остановлена", "сотрудник долго ждёт ответа",
    "срок сегодня", "стандартный приоритет для этого типа проблем",
    "возможный инцидент информационной безопасности", "проблема затрагивает нескольких сотрудников",
})


@dataclass(frozen=True)
class ReplyDraft:
    text: str
    # The closed request whose resolution the draft suggests, for «на основе обращения …».
    based_on: str | None = None


def _first_sentence(text: str, limit: int = 90) -> str:
    sentence = text.split(". ")[0].strip().rstrip(".")
    return sentence if len(sentence) <= limit else sentence[: limit - 1].rstrip() + "…"


def last_resolution(session: Session, playbook_id: str | None, exclude: str) -> tuple[str, str] | None:
    """What a specialist did the last time this kind of request was closed: (summary, request id)."""
    if not playbook_id or playbook_id == "unknown":
        return None
    closed = session.scalars(
        select(Conversation.id).where(
            Conversation.playbook_id == playbook_id, Conversation.resolved_by == "operator",
            Conversation.id != exclude,
        ).order_by(Conversation.resolved_at.desc()).limit(5)
    ).all()
    for conversation_id in closed:
        message = session.scalar(
            select(Message).where(Message.conversation_id == conversation_id, Message.role == "operator",
                                  Message.content.startswith(RESOLUTION_PREFIX))
            .order_by(Message.id.desc()).limit(1)
        )
        if message is not None:
            return message.content[len(RESOLUTION_PREFIX):].strip(), conversation_id
    return None


def draft_reply(session: Session, conversation: Conversation, specialist: User) -> ReplyDraft:
    owner = conversation.owner
    name = owner.first_name if owner else ""
    greeting = f"{name}, здравствуйте!" if name else "Здравствуйте!"
    # Gender-neutral on purpose: the same draft serves every specialist.
    lines = [f"{greeting} Это {specialist.first_name}, специалист поддержки. Ваше обращение у меня в работе."]
    if conversation.urgency in ("high", "critical"):
        # Only what the employee said themselves («встреча через 20 минут»), not the engine's labels.
        said = [part for part in (conversation.urgency_reason or "").split("; ") if part and part not in _ENGINE_REASONS]
        reason = f" ({'; '.join(said)})" if said else ""
        lines.append(f"Понимаю, что это срочно{reason}, — занимаюсь прямо сейчас.")
    tried = [_first_sentence(step.instruction) for step in conversation.steps
             if step.outcome in ("not_helped", "cannot_perform")]
    if tried:
        listed = "; ".join(f"«{step}»" for step in tried[:3])
        lines.append(f"Вижу, что вы уже пробовали: {listed} — повторять это не нужно.")
    found = last_resolution(session, conversation.playbook_id, conversation.id)
    if found is not None:
        summary, source = found
        lines.append(f"В похожем случае помогло: {summary.rstrip('.')}. Проверю то же самое у вас и напишу, как только будет готово.")
        return ReplyDraft("\n\n".join(lines), based_on=source)
    lines.append("Проверю это со своей стороны и напишу, что делать дальше.")
    return ReplyDraft("\n\n".join(lines))
