"""The demo seed must show Incident Radar right away and stay safe to re-run."""

from datetime import timedelta

import pytest
from helpflow_ai import TriageEngine
from helpflow_ai.knowledge import KnowledgeBase
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import utc_now
from app.db.base import Base
from app.models import Conversation, Incident
from app.repositories.conversations import ConversationRepository
from app.seed_demo import seed, seed_incident, seed_showcase, seed_templates
from app.services.admin import AdminService, _aware
from app.services.triage import TriageDialogueService


@pytest.fixture
def factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.drop_all(engine)


def open_incidents(session):
    return session.scalars(select(Incident).where(Incident.status.in_(("CANDIDATE", "ACTIVE")))).all()


def test_seed_shows_a_fresh_vpn_outage(factory):
    assert seed(total=12, session_factory=factory) is True
    assert seed_incident(session_factory=factory) is True

    with factory() as session:
        [incident] = open_incidents(session)
        members = session.scalars(select(Conversation).where(Conversation.incident_id == incident.id)).all()
        assert incident.service == "vpn"
        assert len(members) >= 4
        assert len({member.owner_id for member in members}) == len(members)
        oldest = min(_aware(member.escalated_at) for member in members)
        assert utc_now() - oldest <= timedelta(minutes=30)
        # Some joined on their first message, without any troubleshooting.
        assert any(not member.steps for member in members)


def test_seed_is_idempotent(factory):
    seed(total=12, session_factory=factory)
    seed_incident(session_factory=factory)

    assert seed(total=12, session_factory=factory) is False
    assert seed_incident(session_factory=factory) is False
    with factory() as session:
        assert len(open_incidents(session)) == 1


def test_live_vpn_request_joins_the_seeded_outage(factory):
    seed(total=12, session_factory=factory)
    seed_incident(session_factory=factory)

    with factory() as session:
        dialogue = TriageDialogueService(ConversationRepository(session), TriageEngine(KnowledgeBase.load(), None))
        conversation = dialogue.create_conversation()
        state = dialogue.handle_message(conversation.id, "Не подключается VPN, что делать?")

        assert state.status == "ESCALATED"
        assert state.incident_id == open_incidents(session)[0].id


def test_seeded_metrics_still_load(factory):
    seed(total=12, session_factory=factory)
    seed_incident(session_factory=factory)

    with factory() as session:
        metrics = AdminService(session, "http://localhost").metrics(7)
        assert metrics["total"] >= 5
        assert metrics["open"] >= 4



def seed_all(factory):
    seed(total=12, session_factory=factory)
    seed_incident(session_factory=factory)
    return seed_showcase(session_factory=factory)


def test_showcase_hands_requests_with_screenshots_to_specialists(factory):
    from app.models import Attachment
    from app.services.sla import sla_for

    assert seed_all(factory) is True

    with factory() as session:
        shots = session.scalars(select(Attachment).where(Attachment.content_type == "image/png")).all()
        assert len(shots) >= 3
        conversations = {shot.conversation_id for shot in shots}
        waiting = [session.get(Conversation, cid) for cid in conversations]
        assert all(item.status in {"ESCALATED", "IN_PROGRESS"} for item in waiting)
        assert all(shot.message_id is not None for shot in shots), "each screenshot belongs to the employee's message"
        states = {sla_for(item, utc_now()).state for item in waiting}
        assert {"warning", "breached"} <= states


def test_showcase_has_a_resolved_and_rated_request(factory):
    seed_all(factory)

    with factory() as session:
        rated = session.scalars(select(Conversation).where(
            Conversation.rating_comment == "Быстро и без лишних вопросов, спасибо!",
        )).all()
        assert len(rated) == 1
        item = rated[0]
        assert (item.status, item.resolved_by, item.rating) == ("RESOLVED", "operator", 5)
        assert item.first_operator_reply_at is not None and item.escalated_at is not None


def test_showcase_is_idempotent(factory):
    from app.models import Attachment

    seed_all(factory)
    with factory() as session:
        before = len(session.scalars(select(Attachment)).all())

    assert seed_showcase(session_factory=factory) is False
    with factory() as session:
        assert len(session.scalars(select(Attachment)).all()) == before


def test_starter_templates_are_added_once(factory):
    from app.models import ReplyTemplate

    seed(total=12, session_factory=factory)
    assert seed_templates(session_factory=factory) is True
    assert seed_templates(session_factory=factory) is False
    with factory() as session:
        templates = session.scalars(select(ReplyTemplate)).all()
        assert len(templates) >= 3
        assert any("{имя}" in item.body for item in templates)
