import pytest

from app.api.dependencies.auth import require_employee, require_operator, require_verified_user
from app.core.security import utc_now
from app.main import app
from app.models.auth import User

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PDF = b"%PDF-1.7\n" + b"\x00" * 64


def make_user(db_session, user_id, role, first="Иван", last="Петров"):
    user = User(
        id=user_id, first_name=first, last_name=last, email=f"{user_id}@test.local", department="it",
        password_hash="unused", role=role, email_verified_at=utc_now(),
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def people(db_session, client):
    employee = make_user(db_session, "emp-1", "employee")
    stranger = make_user(db_session, "emp-2", "employee", "Ольга", "Морозова")
    operator = make_user(db_session, "op-1", "operator", "Анна", "Смирнова")
    app.dependency_overrides[require_employee] = lambda: employee
    app.dependency_overrides[require_operator] = lambda: operator
    app.dependency_overrides[require_verified_user] = lambda: employee
    return {"employee": employee, "stranger": stranger, "operator": operator}


def as_viewer(user):
    app.dependency_overrides[require_verified_user] = lambda: user


def upload(client, conversation_id, name="error.png", data=PNG, mime="image/png"):
    return client.post(
        f"/api/conversations/{conversation_id}/attachments",
        files={"file": (name, data, mime)},
    )


def new_conversation(client):
    return client.post("/api/conversations").json()["id"]


def test_upload_returns_metadata_for_an_image(client, people):
    conversation_id = new_conversation(client)

    response = upload(client, conversation_id)

    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "error.png"
    assert body["content_type"] == "image/png"
    assert body["kind"] == "image"
    assert body["size"] == len(PNG)
    assert body["url"] == f"/api/attachments/{body['id']}"


@pytest.mark.parametrize("name, data, mime", [
    ("drawing.svg", b"<svg xmlns='http://www.w3.org/2000/svg'></svg>", "image/svg+xml"),
    ("page.html", b"<html><script>alert(1)</script></html>", "text/html"),
    ("fake.png", b"just some text pretending", "image/png"),
    ("tool.exe", b"MZ\x90\x00" + b"\x00" * 32, "application/octet-stream"),
])
def test_upload_rejects_unsafe_or_mislabelled_files(client, people, name, data, mime):
    conversation_id = new_conversation(client)

    response = upload(client, conversation_id, name, data, mime)

    assert response.status_code == 415


def test_upload_rejects_files_over_the_limit(client, people):
    conversation_id = new_conversation(client)

    response = upload(client, conversation_id, "big.png", PNG + b"\x00" * (10 * 1024 * 1024))

    assert response.status_code == 413


def test_upload_accepts_documents_and_logs(client, people):
    conversation_id = new_conversation(client)

    pdf = upload(client, conversation_id, "report.pdf", PDF, "application/pdf")
    log = upload(client, conversation_id, "vpn.log", "ошибка 809\n".encode(), "text/plain")

    assert pdf.status_code == 201 and pdf.json()["kind"] == "file"
    assert log.status_code == 201 and log.json()["content_type"] == "text/plain"


def test_message_carries_its_attachments(client, people):
    conversation_id = new_conversation(client)
    attachment_id = upload(client, conversation_id).json()["id"]

    response = client.post(f"/api/conversations/{conversation_id}/messages", json={
        "content": "Не подключается VPN, вот скриншот", "attachment_ids": [attachment_id],
    })

    assert response.status_code == 200
    user_message = next(m for m in response.json()["messages"] if m["role"] == "user")
    assert [a["id"] for a in user_message["attachments"]] == [attachment_id]
    assert user_message["attachments"][0]["kind"] == "image"


def test_photo_only_message_asks_for_a_few_words(client, people):
    conversation_id = new_conversation(client)
    attachment_id = upload(client, conversation_id).json()["id"]

    response = client.post(f"/api/conversations/{conversation_id}/messages", json={
        "content": "", "attachment_ids": [attachment_id],
    })

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "NEW"
    assert body["messages"][0]["attachments"]
    assert "в двух словах" in body["messages"][-1]["content"]


def test_message_needs_text_or_a_file(client, people):
    conversation_id = new_conversation(client)

    response = client.post(f"/api/conversations/{conversation_id}/messages", json={"content": "  "})

    assert response.status_code == 422


def test_at_most_five_files_per_message(client, people):
    conversation_id = new_conversation(client)
    ids = [upload(client, conversation_id, f"s{i}.png").json()["id"] for i in range(6)]

    response = client.post(f"/api/conversations/{conversation_id}/messages", json={
        "content": "много скриншотов", "attachment_ids": ids,
    })

    assert response.status_code == 422


def test_cannot_attach_a_file_from_another_conversation(client, people):
    first = new_conversation(client)
    second = new_conversation(client)
    attachment_id = upload(client, first).json()["id"]

    response = client.post(f"/api/conversations/{second}/messages", json={
        "content": "чужой файл", "attachment_ids": [attachment_id],
    })

    assert response.status_code == 409


def test_a_file_is_attached_only_once(client, people):
    conversation_id = new_conversation(client)
    attachment_id = upload(client, conversation_id).json()["id"]
    client.post(f"/api/conversations/{conversation_id}/messages", json={
        "content": "Не работает почта", "attachment_ids": [attachment_id],
    })

    again = client.post(f"/api/conversations/{conversation_id}/messages", json={
        "content": "Да", "attachment_ids": [attachment_id],
    })

    assert again.status_code == 409


def test_download_is_limited_to_the_owner_and_support(client, people):
    conversation_id = new_conversation(client)
    attachment_id = upload(client, conversation_id).json()["id"]
    client.post(f"/api/conversations/{conversation_id}/messages", json={
        "content": "скриншот ошибки", "attachment_ids": [attachment_id],
    })

    own = client.get(f"/api/attachments/{attachment_id}")
    assert own.status_code == 200
    assert own.content == PNG
    assert own.headers["content-type"] == "image/png"
    assert own.headers["x-content-type-options"] == "nosniff"

    as_viewer(people["stranger"])
    assert client.get(f"/api/attachments/{attachment_id}").status_code == 404

    as_viewer(people["operator"])
    assert client.get(f"/api/attachments/{attachment_id}").status_code == 404, "not handed to support yet"

    as_viewer(people["employee"])
    client.post(f"/api/conversations/{conversation_id}/escalate")
    as_viewer(people["operator"])
    assert client.get(f"/api/attachments/{attachment_id}").status_code == 200


def test_files_are_kept_after_escalation_without_an_assistant_reply(client, people):
    conversation_id = new_conversation(client)
    client.post(f"/api/conversations/{conversation_id}/messages", json={"content": "Не работает CRM"})
    client.post(f"/api/conversations/{conversation_id}/escalate")
    attachment_id = upload(client, conversation_id).json()["id"]

    response = client.post(f"/api/conversations/{conversation_id}/messages", json={
        "content": "", "attachment_ids": [attachment_id],
    })

    last = response.json()["messages"][-1]
    assert last["role"] == "user"
    assert last["attachments"][0]["id"] == attachment_id


def test_specialist_can_send_a_file_in_the_same_thread(client, people):
    conversation_id = new_conversation(client)
    client.post(f"/api/conversations/{conversation_id}/messages", json={"content": "Не работает CRM"})
    client.post(f"/api/conversations/{conversation_id}/escalate")
    as_viewer(people["operator"])

    uploaded = client.post(
        f"/api/operator/tickets/{conversation_id}/attachments",
        files={"file": ("how-to.png", PNG, "image/png")},
    )
    assert uploaded.status_code == 201
    reply = client.post(f"/api/operator/tickets/{conversation_id}/messages", json={
        "content": "Вот куда нажать", "attachment_ids": [uploaded.json()["id"]],
    })

    assert reply.status_code == 200
    last = reply.json()["messages"][-1]
    assert last["role"] == "operator"
    assert last["attachments"][0]["filename"] == "how-to.png"


def test_words_after_a_screenshot_become_the_original_request(client, people):
    conversation_id = new_conversation(client)
    attachment_id = upload(client, conversation_id).json()["id"]
    client.post(f"/api/conversations/{conversation_id}/messages", json={"content": "", "attachment_ids": [attachment_id]})

    response = client.post(f"/api/conversations/{conversation_id}/messages", json={
        "content": "Не подключается VPN из дома, ошибка 809",
    })
    client.post(f"/api/conversations/{conversation_id}/escalate")
    card = client.get(f"/api/conversations/{conversation_id}").json()["escalation_card"]

    assert response.json()["service"] == "VPN"
    assert card["original_request"].startswith("Не подключается VPN")
