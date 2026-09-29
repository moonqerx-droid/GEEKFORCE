"""The support lead finds a conversation by its words and deletes it completely."""

import pytest
from sqlalchemy import select

from app.api.dependencies.auth import require_admin
from app.core.security import hash_password, utc_now
from app.main import app
from app.models.attachment import Attachment
from app.models.audit import AdminAuditEvent
from app.models.auth import User
from app.models.conversation import Conversation, Message, TroubleshootingStep

URL = "/api/admin/conversations"


def add_user(db_session, user_id, role):
    user = User(
        id=user_id, first_name="Мария", last_name="Иванова", email=f"{user_id}@example.org",
        department="it", password_hash=hash_password("Pass12345678"), role=role, email_verified_at=utc_now(),
    )
    db_session.add(user)
    db_session.commit()
    return user


def add_conversation(db_session, owner, *texts):
    conversation = Conversation(workflow_version="triage-v1", owner_id=owner.id, status="TROUBLESHOOTING")
    db_session.add(conversation)
    db_session.flush()
    for text in texts:
        db_session.add(Message(conversation_id=conversation.id, role="user", content=text))
    db_session.flush()
    db_session.add(TroubleshootingStep(conversation_id=conversation.id, code="restart", position=1,
                                       instruction="Перезагрузите", outcome="helped"))
    db_session.add(Attachment(conversation_id=conversation.id, filename="a.png", content_type="image/png",
                              size=3, sha256="0" * 64, data=b"png"))
    db_session.commit()
    return conversation.id


@pytest.fixture
def admin(db_session, client):
    user = add_user(db_session, "admin-chats", "admin")
    app.dependency_overrides[require_admin] = lambda: user
    return user


@pytest.fixture
def employee(db_session):
    return add_user(db_session, "employee-chats", "employee")


def test_admin_sees_every_conversation_newest_first(client, admin, employee, db_session):
    first = add_conversation(db_session, employee, "не печатает принтер")
    second = add_conversation(db_session, employee, "vpn не подключается")

    rows = client.get(URL).json()

    assert [row["id"] for row in rows] == [second, first]
    assert rows[0]["owner_email"] == "employee-chats@example.org"
    assert rows[0]["first_message"] == "vpn не подключается"


def test_search_finds_a_conversation_by_any_message(client, admin, employee, db_session):
    add_conversation(db_session, employee, "не печатает принтер")
    rude = add_conversation(db_session, employee, "здравствуйте", "опять этот dumb vpn")

    rows = client.get(URL, params={"q": "dumb"}).json()

    assert [row["id"] for row in rows] == [rude]
    assert "dumb" in rows[0]["match"]


def test_delete_removes_the_conversation_with_everything_in_it(client, admin, employee, db_session):
    doomed = add_conversation(db_session, employee, "грубое сообщение")
    kept = add_conversation(db_session, employee, "нормальное сообщение")

    assert client.delete(f"{URL}/{doomed}").status_code == 204

    db_session.expire_all()
    assert db_session.get(Conversation, doomed) is None
    for model in (Message, TroubleshootingStep, Attachment):
        assert db_session.scalars(select(model).where(model.conversation_id == doomed)).all() == []
    assert db_session.get(Conversation, kept) is not None
    [event] = db_session.scalars(select(AdminAuditEvent).where(
        AdminAuditEvent.action == "conversation_deleted")).all()
    assert event.actor_id == admin.id and event.changes["conversation_id"] == doomed
    assert "грубое" not in str(event.changes)  # the audit never keeps the deleted words


def test_deleting_an_unknown_conversation_is_404(client, admin):
    assert client.delete(f"{URL}/no-such-id").status_code == 404


def test_only_the_support_lead_can_delete(client, employee, db_session):
    conversation = add_conversation(db_session, employee, "текст")
    assert client.delete(f"{URL}/{conversation}").status_code in {401, 403}
    assert client.get(URL).status_code in {401, 403}
