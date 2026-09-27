from app.api.dependencies.auth import require_employee
from app.main import app
from app.models.auth import User
from app.models.conversation import Conversation


def employee(user_id: str):
    return User(id=user_id, first_name="Анна", last_name="Иванова", email=f"{user_id}@example.ru",
                department="it", password_hash="unused", role="employee")


def test_employee_cannot_discover_another_users_conversation(client, db_session):
    other = employee("other-user")
    db_session.add(other)
    db_session.flush()
    conversation = Conversation(owner_id=other.id)
    db_session.add(conversation)
    db_session.commit()

    app.dependency_overrides[require_employee] = lambda: employee("current-user")
    assert client.get(f"/api/conversations/{conversation.id}").status_code == 404
    assert client.post(f"/api/conversations/{conversation.id}/messages", json={"content": "test"}).status_code == 404
