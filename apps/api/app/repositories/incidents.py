from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Conversation, Incident, IncidentUpdate, Message
from app.models.conversation import utc_now


def _aware(value):
    return value if value is None or value.tzinfo else value.replace(tzinfo=utc_now().tzinfo)


class IncidentRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, incident_id: str) -> Incident | None:
        return self.session.scalar(
            select(Incident)
            .where(Incident.id == incident_id)
            .options(selectinload(Incident.updates))
            .execution_options(populate_existing=True)
        )

    def get_conversation(self, conversation_id: str) -> Conversation | None:
        return self.session.scalar(
            select(Conversation)
            .where(Conversation.id == conversation_id)
            .options(selectinload(Conversation.messages), selectinload(Conversation.steps))
            .execution_options(populate_existing=True)
        )

    def list_open(self, service: str) -> list[Incident]:
        statement = (
            select(Incident)
            .where(
                Incident.status.in_(("CANDIDATE", "ACTIVE")),
                Incident.service == service,
            )
            .options(selectinload(Incident.updates))
            .order_by(Incident.id)
        )
        return list(self.session.scalars(statement).all())

    def list_incidents(self, *, include_resolved: bool = False) -> list[Incident]:
        statement = select(Incident).options(selectinload(Incident.updates))
        if not include_resolved:
            statement = statement.where(Incident.status.in_(("CANDIDATE", "ACTIVE")))
        return list(self.session.scalars(statement).all())

    def list_unlinked_escalated(self, service: str, exclude_id: str, since=None) -> list[Conversation]:
        """Requests waiting for or taken by a specialist, not yet in an incident."""
        statement = (
            select(Conversation)
            .where(
                Conversation.status.in_(("ESCALATED", "IN_PROGRESS")),
                Conversation.incident_id.is_(None),
                Conversation.id != exclude_id,
            )
            .options(selectinload(Conversation.messages), selectinload(Conversation.steps))
            .order_by(Conversation.id)
        )
        items = self.session.scalars(statement).all()
        normalized = service.casefold().replace("ё", "е")
        return [
            item for item in items
            if (item.service or "").strip().casefold().replace("ё", "е") == normalized
            and (since is None or _aware(item.escalated_at or item.created_at) >= since)
        ]

    def conversation_ids(self, incident_id: str) -> list[str]:
        return list(self.session.scalars(
            select(Conversation.id)
            .where(Conversation.incident_id == incident_id)
            .order_by(Conversation.id)
        ).all())

    def conversations(self, incident_id: str) -> list[Conversation]:
        return list(self.session.scalars(
            select(Conversation)
            .where(Conversation.incident_id == incident_id)
            .options(selectinload(Conversation.messages), selectinload(Conversation.steps))
            .order_by(Conversation.id)
        ).all())

    @staticmethod
    def link(conversation: Conversation, incident: Incident) -> None:
        if conversation.incident_id is None:
            conversation.incident_id = incident.id
            conversation.updated_at = utc_now()

    def create_candidate(
        self,
        service: str,
        title: str,
        signature_tokens: list[str],
        threshold: float,
    ) -> Incident:
        incident = Incident(
            status="CANDIDATE",
            service=service,
            title=title,
            signature_tokens=signature_tokens,
            similarity_threshold=threshold,
        )
        self.session.add(incident)
        self.session.flush()
        return incident

    def append_message(
        self, conversation: Conversation, message: str, *, role: str = "assistant", author_id: str | None = None,
    ) -> None:
        conversation.messages.append(Message(role=role, content=message, author_id=author_id))
        conversation.updated_at = utc_now()

    def find_update(self, incident_id: str, request_key: str) -> IncidentUpdate | None:
        return self.session.scalar(
            select(IncidentUpdate).where(
                IncidentUpdate.incident_id == incident_id,
                IncidentUpdate.request_key == request_key,
            )
        )

    def create_update(
        self, incident: Incident, *, message: str, request_key: str
    ) -> IncidentUpdate:
        update = IncidentUpdate(
            incident=incident,
            message=message,
            request_key=request_key,
        )
        self.session.add(update)
        return update
