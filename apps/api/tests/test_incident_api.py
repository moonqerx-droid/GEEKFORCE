import pytest

from app.models import Conversation, Incident
from app.repositories.conversations import ConversationRepository


def test_incident_list_orders_open_clusters(client, incident_factory):
    resolved = incident_factory(status="RESOLVED", members=5)
    active = incident_factory(status="ACTIVE", members=4)
    small = incident_factory(status="CANDIDATE", members=2)
    large = incident_factory(status="CANDIDATE", members=3)

    response = client.get("/api/operator/incidents")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [large.id, active.id]
    with_resolved = client.get("/api/operator/incidents?include_resolved=true")
    assert with_resolved.status_code == 200
    assert {item["id"] for item in with_resolved.json()} == {
        resolved.id, active.id, large.id
    }
    resolved_item = next(item for item in with_resolved.json() if item["id"] == resolved.id)
    assert resolved_item["title"] == "CRM: проблема у 5 сотрудников"


def test_incident_title_describes_a_problem_for_unique_employees(client, db_session):
    incident = Incident(
        status="CANDIDATE",
        service="права доступа",
        title="Права доступа не работает",
        signature_tokens=["права", "доступа"],
        similarity_threshold=0.55,
    )
    db_session.add(incident)
    db_session.flush()
    for index in range(3):
        db_session.add(Conversation(
            workflow_version="triage-v1",
            status="ESCALATED",
            service="Права доступа",
            incident_id=incident.id,
            owner_id=f"employee-{index}",
        ))
    db_session.flush()

    [item] = client.get("/api/operator/incidents").json()

    assert item["title"] == "Права доступа: проблема у 3 сотрудников"
    assert "не работает" not in item["title"]


def test_broadcast_reaches_every_member_once(client, candidate):
    payload = {
        "message": "CRM недоступна. Команда уже восстанавливает сервис.",
        "request_key": "demo-update-1",
        "expected_revision": candidate.revision,
    }

    first = client.post(f"/api/operator/incidents/{candidate.id}/broadcast", json=payload)
    replay = client.post(f"/api/operator/incidents/{candidate.id}/broadcast", json=payload)

    assert first.status_code == 200, first.text
    assert replay.status_code == 200, replay.text
    assert replay.json()["delivered_to"] == first.json()["delivered_to"]
    assert replay.json()["incident"]["status"] == "ACTIVE"
    for conversation_id in first.json()["delivered_to"]:
        state = client.get(f"/api/operator/tickets/{conversation_id}").json()
        assert [message["content"] for message in state["messages"]].count(payload["message"]) == 1


def test_broadcast_rejects_stale_and_resolved(client, candidate, resolved_incident):
    stale = {
        "message": "Обновление",
        "request_key": "stale-1",
        "expected_revision": candidate.revision + 1,
    }
    closed = {
        "message": "Обновление",
        "request_key": "closed-1",
        "expected_revision": resolved_incident.revision,
    }

    assert client.post(
        f"/api/operator/incidents/{candidate.id}/broadcast", json=stale
    ).status_code == 409
    assert client.post(
        f"/api/operator/incidents/{resolved_incident.id}/broadcast", json=closed
    ).status_code == 409


def test_broadcast_returns_not_found(client):
    response = client.post("/api/operator/incidents/missing/broadcast", json={
        "message": "Обновление",
        "request_key": "missing-1",
        "expected_revision": 1,
    })

    assert response.status_code == 404
    assert response.json()["detail"] == "Incident not found"


def test_broadcast_rolls_back_partial_delivery(
    db_session, incident_service, candidate, monkeypatch
):
    db_session.commit()
    original = incident_service.repository.append_message
    calls = 0

    def fail_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("write failed")
        return original(*args, **kwargs)

    monkeypatch.setattr(incident_service.repository, "append_message", fail_second)

    with pytest.raises(RuntimeError, match="write failed"):
        incident_service.broadcast(
            candidate.id, "Обновление", "rollback-1", candidate.revision
        )
    db_session.rollback()

    assert incident_service.repository.find_update(candidate.id, "rollback-1") is None
    assert all(
        "Обновление" not in [message.content for message in ConversationRepository(db_session).get(cid).messages]
        for cid in incident_service.repository.conversation_ids(candidate.id)
    )
