import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Incident
from app.models import Conversation, Message
from app.repositories.conversations import ConversationRepository
from app.repositories.incidents import IncidentRepository


def test_three_similar_escalations_form_one_candidate(
    db_session, incident_service, crm_failure_factory
):
    conversations = [crm_failure_factory(code="502") for _ in range(3)]

    results = [incident_service.observe_escalated(item.id) for item in conversations]

    incident = next(result for result in results if result is not None)
    assert incident.status == "CANDIDATE"
    assert incident.service == "crm"
    db_session.flush()
    for item in conversations:
        db_session.refresh(item)
    assert {item.incident_id for item in conversations} == {incident.id}
    assert set(IncidentRepository(db_session).conversation_ids(incident.id)) == {
        item.id for item in conversations
    }


def test_reobserving_member_does_not_duplicate_membership(incident_service, candidate):
    before = incident_service.read(candidate.id).conversation_ids

    incident_service.observe_escalated(before[0])

    assert incident_service.read(candidate.id).conversation_ids == before


def test_different_service_does_not_complete_cluster(
    incident_service, crm_failure_factory, mail_failure_factory
):
    for item in (crm_failure_factory(), crm_failure_factory(), mail_failure_factory()):
        incident_service.observe_escalated(item.id)

    assert incident_service.repository.list_open("crm") == []
    assert incident_service.repository.list_open("корпоративная почта") == []


def test_cluster_create_race_rereads_once(
    db_session, incident_service, crm_failure_factory, monkeypatch
):
    members = [crm_failure_factory() for _ in range(3)]
    competing = Incident(
        status="CANDIDATE",
        service="crm",
        title="Массовая недоступность CRM",
        signature_tokens=["502", "crm", "недоступен"],
        similarity_threshold=0.55,
    )
    db_session.add(competing)
    db_session.flush()
    original_list_open = incident_service.repository.list_open
    list_calls = 0

    def hide_then_reveal(service):
        nonlocal list_calls
        list_calls += 1
        return [] if list_calls == 1 else original_list_open(service)

    monkeypatch.setattr(incident_service.repository, "list_open", hide_then_reveal)
    monkeypatch.setattr(
        incident_service.repository,
        "create_candidate",
        lambda *args, **kwargs: (_ for _ in ()).throw(IntegrityError("race", {}, None)),
    )

    result = incident_service.observe_escalated(members[-1].id)

    assert result is not None
    assert result.id == competing.id
    assert list_calls == 2


def test_signature_failure_rolls_back_membership(
    db_session, incident_service, crm_failure_factory, monkeypatch
):
    members = [crm_failure_factory() for _ in range(3)]
    db_session.commit()
    monkeypatch.setattr(
        incident_service,
        "_recompute_signature",
        lambda *_: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    with pytest.raises(RuntimeError, match="boom"):
        incident_service.observe_escalated(members[-1].id)
    db_session.rollback()

    assert all(
        ConversationRepository(db_session).get(item.id).incident_id is None
        for item in members
    )


def test_first_turn_fields_match_existing_candidate(
    db_session, incident_service, candidate
):
    fourth = Conversation(
        workflow_version="triage-v1",
        status="NEW",
        service="CRM",
        summary="Проблема с CRM: CRM не открывается",
        symptoms=["CRM не открывается"],
        known_facts={"error_text": "502"},
        playbook_id="crm_login_device_specific",
    )
    fourth.messages.append(Message(
        role="user", content="CRM не открывается, у меня ошибка 502"
    ))
    db_session.add(fourth)
    db_session.flush()

    match = incident_service.match_first_turn(fourth.id)

    assert match is not None
    assert match.incident_id == candidate.id
    assert match.score >= 0.55


def test_signature_is_filled_when_the_session_does_not_autoflush(db_session, incident_service, crm_failure_factory):
    # The application's SessionLocal runs with autoflush=False.
    db_session.autoflush = False
    created = None
    for _ in range(3):
        created = incident_service.observe_escalated(crm_failure_factory(code="502").id) or created

    assert created is not None
    assert {"crm", "502"} <= set(created.signature_tokens)
