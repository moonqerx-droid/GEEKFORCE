"""Incident Radar as the three roles see it: specialist, employee, support lead."""

from datetime import timedelta

import pytest

from app.api.dependencies.auth import require_admin, require_operator, require_verified_user
from app.core.security import utc_now
from app.main import app
from app.models import Conversation, Incident, Message
from app.models.auth import User


def make_user(db_session, user_id, role, first_name="Анна", last_name="Смирнова", department="it"):
    user = User(
        id=user_id, first_name=first_name, last_name=last_name, email=f"{user_id}@test.local",
        department=department, password_hash="unused", role=role, email_verified_at=utc_now(),
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def operator_user(db_session):
    # Same id as the operator the client fixture signs in with.
    return make_user(db_session, "test-operator", "operator")


def vpn_request(db_session, owner, *, status="ESCALATED", minutes_ago=5):
    moment = utc_now() - timedelta(minutes=minutes_ago)
    item = Conversation(
        workflow_version="triage-v1", status=status, service="VPN",
        summary="Не подключается VPN", symptoms=["VPN не подключается"],
        known_facts={"error_text": "ошибка 809"}, playbook_id="vpn_connection",
        owner_id=owner.id, created_at=moment, escalated_at=moment,
    )
    item.messages.append(Message(role="user", content="Не подключается VPN, ошибка 809"))
    db_session.add(item)
    db_session.flush()
    return item


@pytest.fixture
def employees(db_session):
    return [
        make_user(db_session, f"emp-{index}", "employee", first_name=name, last_name="Тестов",
                  department="sales")
        for index, name in enumerate(["Иван", "Елена", "Ольга", "Сергей"])
    ]


def cluster(db_session, incident_service, employees, **kwargs):
    incident = None
    for owner in employees[:3]:
        item = vpn_request(db_session, owner, **kwargs)
        incident = incident_service.observe_escalated(item.id) or incident
    db_session.commit()
    return incident


# --- detection --------------------------------------------------------------

def test_old_escalations_do_not_make_an_outage(db_session, incident_service, employees):
    assert cluster(db_session, incident_service, employees, minutes_ago=6 * 60) is None


def test_requests_already_taken_by_a_specialist_still_count(db_session, incident_service, employees):
    first = vpn_request(db_session, employees[0], status="IN_PROGRESS")
    second = vpn_request(db_session, employees[1], status="IN_PROGRESS")
    third = vpn_request(db_session, employees[2])

    incident = incident_service.observe_escalated(third.id)

    assert incident is not None
    assert {first.incident_id, second.incident_id, third.incident_id} == {incident.id}


# --- specialist -------------------------------------------------------------

def test_incident_explains_where_its_requests_come_from(client, db_session, incident_service, employees):
    incident = cluster(db_session, incident_service, employees)

    [item] = client.get("/api/operator/incidents").json()

    assert item["id"] == incident.id
    assert item["service_label"] == "VPN"
    assert item["conversation_count"] == 3
    assert item["affected_employees"] == 3
    assert item["first_seen_at"]
    assert {member["owner_name"] for member in item["members"]} == {
        "Иван Тестов", "Елена Тестов", "Ольга Тестов",
    }
    assert item["members"][0]["original_request"] == "Не подключается VPN, ошибка 809"


def test_specialist_confirms_an_incident(client, db_session, incident_service, employees):
    incident = cluster(db_session, incident_service, employees)

    stale = client.post(f"/api/operator/incidents/{incident.id}/confirm", json={"expected_revision": 99})
    confirmed = client.post(
        f"/api/operator/incidents/{incident.id}/confirm", json={"expected_revision": incident.revision},
    )

    assert stale.status_code == 409
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "ACTIVE"


def test_broadcast_is_a_specialist_message_in_every_chat(
    client, db_session, incident_service, employees, operator_user,
):
    incident = cluster(db_session, incident_service, employees)
    text = "Сервер VPN перезапускаем, минут через 15 всё заработает."

    result = client.post(f"/api/operator/incidents/{incident.id}/broadcast", json={
        "message": text, "request_key": "vpn-1", "expected_revision": incident.revision,
    })

    assert result.status_code == 200, result.text
    for conversation_id in result.json()["delivered_to"]:
        ticket = client.get(f"/api/operator/tickets/{conversation_id}").json()
        last = ticket["messages"][-1]
        assert (last["role"], last["content"], last["author_name"]) == ("operator", text, "Анна Смирнова")
        assert ticket["first_operator_reply_at"] is not None
        assert ticket["status"] == "ESCALATED", "a broadcast does not assign every request to one person"


def test_resolving_an_incident_closes_its_requests(client, db_session, incident_service, employees, operator_user):
    incident = cluster(db_session, incident_service, employees)
    ids = [conversation.id for conversation in db_session.query(Conversation).filter_by(incident_id=incident.id)]

    response = client.post(f"/api/operator/incidents/{incident.id}/resolve", json={
        "message": "VPN снова работает. Проверьте, пожалуйста, у себя.",
        "expected_revision": incident.revision,
    })

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "RESOLVED"
    assert client.get("/api/operator/incidents").json() == []
    for conversation_id in ids:
        ticket = client.get(f"/api/operator/tickets/{conversation_id}").json()
        assert ticket["status"] == "RESOLVED"
        assert ticket["resolved_by"] == "operator"
        assert ticket["messages"][-1]["content"] == "VPN снова работает. Проверьте, пожалуйста, у себя."
    again = client.post(f"/api/operator/incidents/{incident.id}/resolve", json={
        "message": "ещё раз", "expected_revision": response.json()["revision"],
    })
    assert again.status_code == 409


def test_employees_cannot_see_the_radar(client, db_session, employees):
    app.dependency_overrides.pop(require_operator)
    app.dependency_overrides[require_verified_user] = lambda: employees[0]

    assert client.get("/api/operator/incidents").status_code == 403


# --- employee ---------------------------------------------------------------

def test_matching_first_message_says_it_is_a_known_outage(client, db_session, incident_service, employees):
    cluster(db_session, incident_service, employees)
    cid = client.post("/api/conversations").json()["id"]

    state = client.post(f"/api/conversations/{cid}/messages", json={
        "content": "VPN не подключается, пишет ошибка 809",
    }).json()

    assert state["status"] == "ESCALATED"
    assert state["incident_id"]
    assert state["escalated_at"]
    notice = state["messages"][-1]["content"]
    assert notice.startswith("Похоже, это общий сбой: VPN не работает у нескольких коллег")
    assert "специалисты уже чинят" in notice


def test_joining_a_confirmed_outage_repeats_its_latest_update(
    client, db_session, incident_service, employees, operator_user,
):
    incident = cluster(db_session, incident_service, employees)
    client.post(f"/api/operator/incidents/{incident.id}/broadcast", json={
        "message": "Чиним сервер VPN, ориентир 15 минут.", "request_key": "vpn-1",
        "expected_revision": incident.revision,
    })
    cid = client.post("/api/conversations").json()["id"]

    state = client.post(f"/api/conversations/{cid}/messages", json={
        "content": "VPN не подключается, пишет ошибка 809",
    }).json()

    assert "Чиним сервер VPN, ориентир 15 минут." in state["messages"][-1]["content"]


# --- support lead -----------------------------------------------------------

def test_metrics_stay_consistent_through_an_outage(client, db_session, incident_service, employees, operator_user):
    admin = make_user(db_session, "admin-1", "admin", first_name="Мария", last_name="Иванова")
    app.dependency_overrides[require_admin] = lambda: admin
    before = client.get("/api/admin/metrics?days=7").json()
    incident = cluster(db_session, incident_service, employees)
    client.post(f"/api/operator/incidents/{incident.id}/broadcast", json={
        "message": "Чиним.", "request_key": "vpn-1", "expected_revision": incident.revision,
    })
    revision = db_session.get(Incident, incident.id).revision
    client.post(f"/api/operator/incidents/{incident.id}/resolve", json={
        "message": "Починили.", "expected_revision": revision,
    })

    after = client.get("/api/admin/metrics?days=7")

    assert after.status_code == 200, after.text
    body = after.json()
    assert body["total"] == before["total"] + 3
    assert body["resolved_by_operator"] == before["resolved_by_operator"] + 3
    assert body["open"] == before["open"]
    assert body["median_first_reply_minutes"] is not None
