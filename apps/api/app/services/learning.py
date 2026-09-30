"""Learning from closed requests: a specialist's resolution becomes a scenario step once the
support lead rewrites it for employees and approves it. The next employee with the same problem
tries it before waiting for a specialist; the dashboard's escalation rate by topic shows the effect."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit import AdminAuditEvent
from app.models.auth import User
from app.models.conversation import Conversation, Message
from app.models.learned_step import LearnedStep
from app.services.reply_draft import RESOLUTION_PREFIX


class LearningRefused(ValueError):
    pass


class LearnedStepNotFound(LookupError):
    pass


@dataclass(frozen=True)
class Suggestion:
    conversation_id: str
    playbook_id: str
    playbook_title: str
    request: str
    resolution: str
    specialist: str | None
    resolved_at: datetime | None


class LearningService:
    def __init__(self, session: Session, playbook_titles: dict[str, str]):
        self.session = session
        self.titles = playbook_titles

    def suggestions(self, limit: int = 20) -> list[Suggestion]:
        """Resolutions of closed requests that are not yet a step, newest first."""
        used = set(self.session.scalars(select(LearnedStep.source_conversation_id)).all())
        closed = self.session.scalars(
            select(Conversation).where(
                Conversation.resolved_by == "operator", Conversation.playbook_id.is_not(None),
                Conversation.playbook_id != "unknown",
            ).order_by(Conversation.resolved_at.desc()).limit(limit * 3)
        ).all()
        found: list[Suggestion] = []
        for conversation in closed:
            if conversation.id in used or conversation.playbook_id not in self.titles:
                continue
            ordered = sorted(conversation.messages, key=lambda message: message.id)
            resolution = next((m.content[len(RESOLUTION_PREFIX):].strip() for m in reversed(ordered)
                               if m.role == "operator" and m.content.startswith(RESOLUTION_PREFIX)), None)
            if not resolution:
                continue
            request = next((m.content for m in ordered if m.role == "user" and m.content.strip()), "")
            found.append(Suggestion(
                conversation_id=conversation.id, playbook_id=conversation.playbook_id,
                playbook_title=self.titles[conversation.playbook_id], request=request[:300],
                resolution=resolution, specialist=conversation.assignee.full_name if conversation.assignee else None,
                resolved_at=conversation.resolved_at,
            ))
            if len(found) == limit:
                break
        return found

    def steps(self) -> list[LearnedStep]:
        return list(self.session.scalars(select(LearnedStep).order_by(LearnedStep.created_at.desc())).all())

    def add(self, playbook_id: str, instruction: str, actor: User,
            source_conversation_id: str | None = None) -> LearnedStep:
        text = " ".join(instruction.split())
        if playbook_id not in self.titles or playbook_id == "unknown":
            raise LearningRefused("Такого сценария нет.")
        if not 10 <= len(text) <= 600:
            raise LearningRefused("Опишите шаг для сотрудника: от 10 до 600 символов.")
        resolution = None
        if source_conversation_id:
            source = self.session.get(Conversation, source_conversation_id)
            if source is not None:
                resolution = next((m.content[len(RESOLUTION_PREFIX):].strip() for m in source.messages
                                   if m.role == "operator" and m.content.startswith(RESOLUTION_PREFIX)), None)
        step = LearnedStep(playbook_id=playbook_id, instruction=text, source_conversation_id=source_conversation_id,
                           source_resolution=resolution, created_by=actor.id)
        self.session.add(step)
        self.session.flush()
        self.session.add(AdminAuditEvent(actor_id=actor.id, action="learned_step_added", changes={
            "step_id": step.id, "playbook_id": playbook_id, "source_conversation_id": source_conversation_id,
        }))
        self.session.commit()
        return step

    def remove(self, step_id: str, actor: User) -> None:
        step = self.session.get(LearnedStep, step_id)
        if step is None:
            raise LearnedStepNotFound(step_id)
        self.session.add(AdminAuditEvent(actor_id=actor.id, action="learned_step_removed", changes={
            "step_id": step.id, "playbook_id": step.playbook_id,
        }))
        self.session.delete(step)
        self.session.commit()


def engine_items(session: Session) -> list[dict]:
    """Approved steps in the shape `TriageEngine.set_learned_steps` expects, oldest first."""
    return [{"id": step.id, "playbook_id": step.playbook_id, "instruction": step.instruction}
            for step in session.scalars(select(LearnedStep).order_by(LearnedStep.created_at)).all()]
