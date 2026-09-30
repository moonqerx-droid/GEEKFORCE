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


def test_seed_loads_the_demo_company_documents(factory):
    from app.models.knowledge import KnowledgeDocument
    from app.seed_demo import seed_documents

    seed(total=12, session_factory=factory)

    from app.seed_demo import DOCUMENT_TITLES

    # seed() loads them before playing the history; a second run adds nothing.
    assert len(DOCUMENT_TITLES) == 10
    assert seed_documents(session_factory=factory) == 0, "a second run adds nothing"
    with factory() as session:
        documents = session.query(KnowledgeDocument).all()
        assert sorted(d.title for d in documents) == sorted(DOCUMENT_TITLES.values())
        assert all(d.status == "ready" and d.chunks for d in documents)


def test_an_edited_document_replaces_the_earlier_upload(factory, tmp_path):
    from app.models.knowledge import KnowledgeDocument
    from app.seed_demo import seed_documents

    seed(total=4, session_factory=factory)
    rules = tmp_path / "travel-regulations.md"
    rules.write_text("# Командировки\n\nСуточные по России — 700 рублей в день.\n", encoding="utf-8")
    assert seed_documents(session_factory=factory, directory=tmp_path) == 1
    rules.write_text("# Командировки\n\nСуточные по России — 900 рублей в день.\n", encoding="utf-8")
    assert seed_documents(session_factory=factory, directory=tmp_path) == 1

    with factory() as session:
        [document] = session.query(KnowledgeDocument).filter_by(title="Регламент командировок").all()
        assert "900 рублей" in document.chunks[0].text  # the stale 700 is gone, not quoted next to it


def test_employee_gets_an_answer_from_a_seeded_document(factory):
    from app.seed_demo import seed_documents

    seed(total=12, session_factory=factory)
    seed_documents(session_factory=factory)
    with factory() as session:
        service = TriageDialogueService(ConversationRepository(session), TriageEngine(KnowledgeBase.load(), None))
        conversation = service.create_conversation()
        session.commit()
        answered = service.handle_message(conversation.id, "Какие суточные положены в командировке по России?")

    assert answered.answer_kind == "document"
    assert "700 рублей" in answered.messages[-1].content



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



def test_the_seeded_history_answers_from_the_documents(factory):
    """History and live answers agree: no «в документах нет» from before the documents were loaded."""
    from app.models.conversation import Message

    seed(total=60, session_factory=factory)
    with factory() as session:
        vacation = session.query(Message).filter(Message.content.like("%отпуск%"), Message.role == "user").all()
        for asked in vacation:
            reply = session.query(Message).filter(
                Message.conversation_id == asked.conversation_id, Message.id > asked.id,
                Message.role == "assistant").order_by(Message.id).first()
            assert reply is None or "ответа на этот вопрос нет" not in reply.content, asked.content


def test_reset_history_replays_it_for_the_same_people(factory):
    from app.models.auth import User
    from app.seed_demo import reset_history

    seed(total=8, session_factory=factory)
    seed_incident(session_factory=factory)
    with factory() as session:
        people = session.query(User).count()
    assert reset_history(session_factory=factory) > 0
    with factory() as session:
        assert session.query(Conversation).count() == 0 and not open_incidents(session)
    assert seed(total=8, session_factory=factory) is True
    with factory() as session:
        assert session.query(User).count() == people  # nobody duplicated
        assert session.query(Conversation).count() == 8


def test_a_seeded_resolution_belongs_to_its_scenario(factory):
    """The reply draft quotes these: a phishing report must not be «fixed» with VPN certificates."""
    from app.models.conversation import Message
    from app.seed_demo import GENERIC_RESOLUTION, RESOLUTIONS

    seed(total=60, session_factory=factory)
    with factory() as session:
        closed = session.query(Conversation).filter(Conversation.resolved_by == "operator").all()
        assert closed
        for conversation in closed:
            summary = session.query(Message).filter(
                Message.conversation_id == conversation.id,
                Message.content.like("Обращение закрыто. Итог: %")).one().content.split("Итог: ", 1)[1]
            allowed = RESOLUTIONS.get(conversation.playbook_id) or [GENERIC_RESOLUTION]
            assert summary in allowed, (conversation.playbook_id, summary)
