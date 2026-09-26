from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from helpflow_ai import KnowledgeBase, TriageEngine
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.repositories.conversations import ConversationRepository
from app.services.dialogue import DialogueConflict
from app.services.triage import TriageDialogueService


def prepare_step(client):
    cid = client.post("/api/conversations").json()["id"]
    client.post(f"/api/conversations/{cid}/messages", json={"content": "CRM не работает, срочно"})
    return client.post(f"/api/conversations/{cid}/messages", json={"content": "Ошибка 403"}).json()


def test_replayed_step_result_is_rejected_without_advancing(client):
    before = prepare_step(client)
    payload = {"outcome": "not_helped", "expected_revision": before["revision"],
               "step_code": before["current_step"]["code"]}
    endpoint = f"/api/conversations/{before['id']}/step-result"
    first = client.post(endpoint, json=payload)
    assert first.status_code == 200
    assert client.post(endpoint, json=payload).status_code == 409
    after = client.get(f"/api/conversations/{before['id']}").json()
    assert after == first.json()
    assert len(after["completed_steps"]) == 1


def test_stale_message_is_rejected_without_history_changes(client):
    before = client.post("/api/conversations").json()
    payload = {"content": "Не работает VPN", "expected_revision": before["revision"]}
    endpoint = f"/api/conversations/{before['id']}/messages"
    first = client.post(endpoint, json=payload)
    assert first.status_code == 200
    assert client.post(endpoint, json=payload).status_code == 409
    assert client.get(f"/api/conversations/{before['id']}").json() == first.json()


def test_wrong_step_code_is_rejected(client):
    before = prepare_step(client)
    result = client.post(f"/api/conversations/{before['id']}/step-result",
                         json={"outcome": "helped", "step_code": "old_step"})
    assert result.status_code == 409
    assert client.get(f"/api/conversations/{before['id']}").json() == before


def test_concurrent_turns_have_only_one_winner(tmp_path):
    database = create_engine(f"sqlite:///{tmp_path / 'concurrent.db'}",
                             connect_args={"check_same_thread": False})
    Base.metadata.create_all(database)
    ai = TriageEngine(KnowledgeBase.load())
    with Session(database, autoflush=False, expire_on_commit=False) as session:
        service = TriageDialogueService(ConversationRepository(session), ai)
        cid = service.create_conversation().id
        service.handle_message(cid, "CRM не работает, срочно")

    barrier = Barrier(2)
    class SimultaneousAI(TriageEngine):
        def decide(self, context):
            decision = super().decide(context)
            barrier.wait(timeout=10)
            return decision

    def reply():
        with Session(database, autoflush=False, expire_on_commit=False) as session:
            service = TriageDialogueService(ConversationRepository(session), SimultaneousAI(ai.kb))
            try:
                service.handle_message(cid, "Ошибка 403")
                return "saved"
            except DialogueConflict:
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: reply(), range(2)))
    assert sorted(outcomes) == ["conflict", "saved"]
    with Session(database) as session:
        conversation = ConversationRepository(session).get(cid)
        assert len(conversation.messages) == 4
        assert conversation.status == "TROUBLESHOOTING"
    database.dispose()
