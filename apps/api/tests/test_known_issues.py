"""Employees see confirmed outages before writing, like a status page."""


def test_only_confirmed_outages_are_shown_to_employees(client, incident_factory):
    incident_factory(status="CANDIDATE", members=3)
    active = incident_factory(status="ACTIVE", members=4)
    incident_factory(status="RESOLVED", members=3)

    response = client.get("/api/known-issues")

    assert response.status_code == 200, response.text
    issues = response.json()
    assert [issue["id"] for issue in issues] == [active.id]
    issue = issues[0]
    assert issue["service"] == "CRM"
    assert issue["affected"] == 4
    assert issue["since"]
    assert issue["update"] is None
    # Employees get what helps them, not the radar internals.
    assert "signature_tokens" not in issue and "members" not in issue


def test_latest_specialist_update_is_shown(client, incident_factory, db_session):
    from app.models.incident import IncidentUpdate

    active = incident_factory(status="ACTIVE", members=3)
    db_session.add(IncidentUpdate(incident_id=active.id, message="Перезапускаем сервер, ждём 20 минут", request_key="u1"))
    db_session.flush()

    issue = client.get("/api/known-issues").json()[0]

    assert issue["update"] == "Перезапускаем сервер, ждём 20 минут"
