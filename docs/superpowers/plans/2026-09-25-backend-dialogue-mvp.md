# Backend and Dialogue MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a cross-platform FastAPI MVP with persistent dialogue state, a deterministic mock AI workflow, escalation, tests, and a minimal browser-based debug interface.

**Architecture:** A single FastAPI service owns the HTTP API, SQLite persistence, dialogue state machine, and static debug page. AI behavior sits behind an `AIService` protocol so the deterministic implementation can later be replaced by the teammate's LLM integration without changing routes or frontend contracts.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Pydantic 2, SQLite, Alembic, pytest, HTTPX, vanilla HTML/CSS/JavaScript, Docker Compose.

**Spec:** `PROJECT_PLAN.md`

## Global Constraints

- The application must run on macOS and Windows through Docker Desktop with `docker compose up --build`.
- Local development must also work with Python 3.12 and `uvicorn` without Docker.
- The initial database is SQLite; database access must remain compatible with later PostgreSQL migration.
- Dialogue transitions are controlled by backend code, never by free-form LLM output.
- The debug UI is an API test harness, not the team's final visual frontend.
- No external AI key is required for the MVP; `AI_PROVIDER=mock` is the default.
- API responses are typed Pydantic contracts and exposed through `/openapi.json`.

## Review Focus

- Empty or whitespace-only user messages return HTTP 422 and do not create messages.
- An unknown conversation ID returns HTTP 404 rather than HTTP 500.
- A step result submitted in the wrong dialogue state returns HTTP 409 and does not mutate state.
- Repeated requests preserve message and step history instead of replacing it.
- Escalation works from any active non-terminal state and is idempotent after reaching `ESCALATED`.

---

## Planned File Structure

```text
apps/api/
├── app/
│   ├── api/routes/
│   │   ├── conversations.py
│   │   ├── health.py
│   │   └── operator.py
│   ├── core/config.py
│   ├── db/base.py
│   ├── db/session.py
│   ├── models/conversation.py
│   ├── repositories/conversations.py
│   ├── schemas/conversation.py
│   ├── services/ai.py
│   ├── services/dialogue.py
│   ├── static/debug.css
│   ├── static/debug.js
│   ├── templates/debug.html
│   └── main.py
├── tests/
│   ├── conftest.py
│   ├── test_conversations.py
│   ├── test_dialogue.py
│   ├── test_health.py
│   └── test_operator.py
├── Dockerfile
├── alembic.ini
├── pyproject.toml
└── requirements.txt
.env.example
docker-compose.yml
README.md
```

## Task 1: Runnable FastAPI Skeleton

**Files:**
- Create: `apps/api/pyproject.toml`
- Create: `apps/api/requirements.txt`
- Create: `apps/api/app/__init__.py`
- Create: `apps/api/app/main.py`
- Create: `apps/api/app/api/routes/health.py`
- Create: `apps/api/tests/conftest.py`
- Create: `apps/api/tests/test_health.py`

**Interfaces:**
- Produces: `app.main.app: FastAPI`, `GET /health -> {"status": "ok"}`.

- [ ] **Step 1: Add the Python test configuration and failing health test**

```python
def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: Run the test and verify RED**

Run: `cd apps/api && pytest tests/test_health.py -v`

Expected: collection fails because `app.main` does not exist.

- [ ] **Step 3: Implement the minimal application and health route**

```python
from fastapi import APIRouter

router = APIRouter()

@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 4: Run the focused and full suites**

Run: `cd apps/api && pytest tests/test_health.py -v && pytest -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add apps/api
git commit -m "feat(api): add FastAPI health endpoint"
```

## Task 2: Configuration and SQLite Persistence

**Files:**
- Create: `apps/api/app/core/config.py`
- Create: `apps/api/app/db/base.py`
- Create: `apps/api/app/db/session.py`
- Create: `apps/api/app/models/conversation.py`
- Create: `apps/api/tests/test_database.py`
- Modify: `apps/api/tests/conftest.py`

**Interfaces:**
- Produces: `Settings.database_url`, `Conversation`, `Message`, `TroubleshootingStep`, `get_db()`.

- [ ] **Step 1: Write failing persistence tests**

```python
def test_conversation_and_messages_persist(db_session):
    conversation = Conversation(status="NEW")
    conversation.messages.append(Message(role="user", content="Не работает CRM"))
    db_session.add(conversation)
    db_session.commit()
    db_session.refresh(conversation)
    assert conversation.id is not None
    assert conversation.messages[0].content == "Не работает CRM"
```

- [ ] **Step 2: Run the test and verify RED**

Run: `cd apps/api && pytest tests/test_database.py -v`

Expected: import failure for the missing model.

- [ ] **Step 3: Implement SQLAlchemy models and test-session dependency**

Use UUID strings for public IDs, UTC timestamps, JSON columns for lists/dictionaries, and cascade deletion for child messages and steps.

- [ ] **Step 4: Verify persistence and full suite**

Run: `cd apps/api && pytest tests/test_database.py -v && pytest -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app apps/api/tests
git commit -m "feat(api): add SQLite conversation persistence"
```

## Task 3: Typed Contracts and Conversation Repository

**Files:**
- Create: `apps/api/app/schemas/conversation.py`
- Create: `apps/api/app/repositories/conversations.py`
- Create: `apps/api/tests/test_repository.py`

**Interfaces:**
- Consumes: SQLAlchemy models and `Session`.
- Produces: `ConversationStatus`, `Urgency`, `MessageRole`, `StepOutcome`, `ConversationRepository.create()`, `.get()`, `.add_message()`, `.add_step_result()`.

- [ ] **Step 1: Write failing repository tests**

```python
def test_repository_preserves_message_history(repository):
    item = repository.create()
    repository.add_message(item.id, role="user", content="Первая")
    repository.add_message(item.id, role="assistant", content="Вторая")
    loaded = repository.get(item.id)
    assert [message.content for message in loaded.messages] == ["Первая", "Вторая"]
```

Add tests proving unknown IDs return `None` and stored steps keep their outcome.

- [ ] **Step 2: Run and verify RED**

Run: `cd apps/api && pytest tests/test_repository.py -v`

Expected: import failure for the missing repository.

- [ ] **Step 3: Implement the repository and Pydantic contracts**

Contracts must use the exact public enum strings from `PROJECT_PLAN.md` and reject empty message content with `min_length=1` plus whitespace validation.

- [ ] **Step 4: Verify focused and full suites**

Run: `cd apps/api && pytest tests/test_repository.py -v && pytest -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app apps/api/tests
git commit -m "feat(api): add dialogue contracts and repository"
```

## Task 4: Deterministic AI Service and Dialogue State Machine

**Files:**
- Create: `apps/api/app/services/ai.py`
- Create: `apps/api/app/services/dialogue.py`
- Create: `apps/api/tests/test_dialogue.py`

**Interfaces:**
- Produces: `AIAnalysis`, `AIService` protocol, `MockAIService`, `DialogueService.handle_message()`, `.record_step_result()`, `.escalate()`.

- [ ] **Step 1: Write failing CRM analysis tests**

```python
def test_mock_ai_detects_urgent_crm_request(mock_ai):
    result = mock_ai.analyze("Не могу войти в CRM с ноутбука. Через 20 минут встреча")
    assert result.service == "CRM"
    assert result.urgency == "high"
    assert result.recommended_playbook == "crm_login_device_specific"
```

Add tests for a non-CRM fallback and for whitespace input rejection.

- [ ] **Step 2: Run the analysis tests and verify RED**

Run: `cd apps/api && pytest tests/test_dialogue.py -k mock_ai -v`

Expected: import failure for `MockAIService`.

- [ ] **Step 3: Implement the minimal deterministic analysis**

Recognize CRM keywords, device-specific symptoms, meeting-time urgency, and a generic fallback. Return typed data rather than prose-only output.

- [ ] **Step 4: Write failing transition tests**

```python
def test_unsuccessful_step_selects_next_step(dialogue, conversation):
    dialogue.handle_message(conversation.id, "Не могу войти в CRM, встреча через 20 минут")
    dialogue.handle_message(conversation.id, "Ошибка соединения")
    updated = dialogue.record_step_result(conversation.id, "not_helped")
    assert updated.status == "TROUBLESHOOTING"
    assert len(updated.completed_steps) == 1
    assert updated.current_step.code == "try_private_window"
```

Add tests for `helped -> VERIFYING -> RESOLVED`, invalid step-state conflict, and escalation idempotency.

- [ ] **Step 5: Run transition tests and verify RED**

Run: `cd apps/api && pytest tests/test_dialogue.py -k dialogue -v`

Expected: failure because `DialogueService` is missing.

- [ ] **Step 6: Implement the state machine**

Allowed transitions:

```text
NEW -> ANALYZING -> CLARIFYING
CLARIFYING -> TROUBLESHOOTING
TROUBLESHOOTING -> TROUBLESHOOTING | VERIFYING | ESCALATED
VERIFYING -> RESOLVED | TROUBLESHOOTING | ESCALATED
```

Illegal events raise a domain `DialogueConflict` exception.

- [ ] **Step 7: Verify the full suite**

Run: `cd apps/api && pytest -v`

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add apps/api/app/services apps/api/tests/test_dialogue.py
git commit -m "feat(dialogue): add mock AI and state machine"
```

## Task 5: Conversation HTTP API

**Files:**
- Create: `apps/api/app/api/routes/conversations.py`
- Create: `apps/api/tests/test_conversations.py`
- Modify: `apps/api/app/main.py`
- Modify: `apps/api/app/schemas/conversation.py`

**Interfaces:**
- Produces: the five conversation endpoints defined in `PROJECT_PLAN.md`.

- [ ] **Step 1: Write failing endpoint tests**

```python
def test_create_and_send_message(client):
    created = client.post("/api/conversations").json()
    response = client.post(
        f"/api/conversations/{created['id']}/messages",
        json={"content": "Не работает CRM, встреча через 20 минут"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "CLARIFYING"
```

Add exact tests for HTTP 404, whitespace HTTP 422, step-result HTTP 409 in the wrong state, and idempotent escalation.

- [ ] **Step 2: Run endpoint tests and verify RED**

Run: `cd apps/api && pytest tests/test_conversations.py -v`

Expected: HTTP 404 because the routes are absent.

- [ ] **Step 3: Implement thin routes over `DialogueService`**

Map missing conversations to HTTP 404 and `DialogueConflict` to HTTP 409. Do not duplicate state logic in route functions.

- [ ] **Step 4: Verify endpoint and full suites**

Run: `cd apps/api && pytest tests/test_conversations.py -v && pytest -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app apps/api/tests/test_conversations.py
git commit -m "feat(api): expose conversation workflow endpoints"
```

## Task 6: Operator Queue and Escalation Card

**Files:**
- Create: `apps/api/app/api/routes/operator.py`
- Create: `apps/api/tests/test_operator.py`
- Modify: `apps/api/app/main.py`
- Modify: `apps/api/app/repositories/conversations.py`

**Interfaces:**
- Produces: `GET /api/operator/tickets`, sorted by urgency then creation time.

- [ ] **Step 1: Write the failing operator test**

```python
def test_operator_queue_returns_escalated_ticket_with_context(client):
    conversation_id = create_escalated_conversation(client)
    response = client.get("/api/operator/tickets")
    assert response.status_code == 200
    ticket = response.json()[0]
    assert ticket["id"] == conversation_id
    assert ticket["original_request"]
    assert ticket["messages"]
    assert ticket["completed_steps"]
    assert ticket["escalation_summary"]
```

- [ ] **Step 2: Run and verify RED**

Run: `cd apps/api && pytest tests/test_operator.py -v`

Expected: HTTP 404 because the operator route is absent.

- [ ] **Step 3: Implement escalation summary and operator queue**

The mock summary must be deterministic and include service, urgency, user facts, questions, answers, and performed steps.

- [ ] **Step 4: Verify focused and full suites**

Run: `cd apps/api && pytest tests/test_operator.py -v && pytest -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app apps/api/tests/test_operator.py
git commit -m "feat(operator): add escalation queue and context card"
```

## Task 7: Minimal Debug Web Interface

**Files:**
- Create: `apps/api/app/templates/debug.html`
- Create: `apps/api/app/static/debug.css`
- Create: `apps/api/app/static/debug.js`
- Create: `apps/api/tests/test_debug_page.py`
- Modify: `apps/api/app/main.py`

**Interfaces:**
- Consumes: conversation HTTP endpoints.
- Produces: `GET /debug`, browser chat, step-result buttons, escalation button, live JSON panel.

- [ ] **Step 1: Write failing page test**

```python
def test_debug_page_contains_workflow_controls(client):
    response = client.get("/debug")
    assert response.status_code == 200
    assert "Создать диалог" in response.text
    assert "Не помогло" in response.text
    assert "Передать специалисту" in response.text
    assert "Debug JSON" in response.text
```

- [ ] **Step 2: Run and verify RED**

Run: `cd apps/api && pytest tests/test_debug_page.py -v`

Expected: HTTP 404 because `/debug` is absent.

- [ ] **Step 3: Implement accessible HTML/CSS/JavaScript**

The page creates a conversation, sends messages through `fetch`, renders assistant messages, disables invalid controls based on status, and prints the latest response as formatted JSON.

- [ ] **Step 4: Verify page and full suites**

Run: `cd apps/api && pytest tests/test_debug_page.py -v && pytest -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app apps/api/tests/test_debug_page.py
git commit -m "feat(debug-ui): add browser workflow harness"
```

## Task 8: Cross-Platform Packaging and Documentation

**Files:**
- Create: `apps/api/Dockerfile`
- Create: `docker-compose.yml`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `README.md`
- Create: `.github/workflows/backend.yml`
- Modify: `apps/api/app/core/config.py`

**Interfaces:**
- Produces: `docker compose up --build`, documented local startup, CI test job.

- [ ] **Step 1: Write configuration tests**

```python
def test_default_configuration_uses_mock_ai_and_sqlite():
    settings = Settings(_env_file=None)
    assert settings.ai_provider == "mock"
    assert settings.database_url.startswith("sqlite")
```

- [ ] **Step 2: Run and verify RED**

Run: `cd apps/api && pytest tests/test_config.py -v`

Expected: failure until the exact defaults are implemented.

- [ ] **Step 3: Add packaging and startup files**

Container command:

```text
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Compose must mount a named volume for SQLite data and expose port `8000`.

- [ ] **Step 4: Add README commands**

Document:

```bash
docker compose up --build
```

and the Python 3.12 local workflow for macOS, PowerShell, and cmd.exe. Include `/health`, `/docs`, `/debug`, and test commands.

- [ ] **Step 5: Verify tests and Docker build**

Run:

```bash
cd apps/api && pytest -v
cd ../.. && docker compose config
docker compose build
```

Expected: tests pass, Compose configuration validates, image builds successfully.

- [ ] **Step 6: Run a smoke test**

Start the service and verify:

```bash
curl http://localhost:8000/health
curl -I http://localhost:8000/debug
```

Expected: health JSON contains `{"status":"ok"}` and the debug page returns HTTP 200.

- [ ] **Step 7: Commit**

```bash
git add .
git commit -m "build(api): add cross-platform Docker workflow"
```

## Task 9: End-to-End Acceptance Test and Final Verification

**Files:**
- Create: `apps/api/tests/test_acceptance_flow.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: the complete public API.
- Produces: an executable proof of the main CRM scenario.

- [ ] **Step 1: Write the acceptance test**

```python
def test_urgent_crm_problem_reaches_resolution(client):
    conversation = client.post("/api/conversations").json()
    cid = conversation["id"]
    analyzed = client.post(
        f"/api/conversations/{cid}/messages",
        json={"content": "Не могу войти в CRM с ноутбука, через 20 минут встреча"},
    ).json()
    assert analyzed["urgency"] == "high"
    assert analyzed["status"] == "CLARIFYING"

    troubleshooting = client.post(
        f"/api/conversations/{cid}/messages",
        json={"content": "Пишет: ошибка соединения"},
    ).json()
    assert troubleshooting["status"] == "TROUBLESHOOTING"

    retry = client.post(
        f"/api/conversations/{cid}/step-result",
        json={"outcome": "not_helped"},
    ).json()
    assert retry["status"] == "TROUBLESHOOTING"

    verifying = client.post(
        f"/api/conversations/{cid}/step-result",
        json={"outcome": "helped"},
    ).json()
    assert verifying["status"] == "VERIFYING"

    resolved = client.post(
        f"/api/conversations/{cid}/messages",
        json={"content": "Да, доступ восстановился"},
    ).json()
    assert resolved["status"] == "RESOLVED"
```

- [ ] **Step 2: Run and verify the acceptance test against the implementation**

Run: `cd apps/api && pytest tests/test_acceptance_flow.py -v`

Expected: the test passes only if every layer is integrated.

- [ ] **Step 3: Run all quality gates**

Run:

```bash
cd apps/api
pytest -v
python -m compileall app
```

Expected: zero failures and successful bytecode compilation.

- [ ] **Step 4: Verify repository state and contract exposure**

Run the application and open `/docs`; confirm every route in Section 8 of `PROJECT_PLAN.md` that belongs to this backend phase is present. Record the working URLs in `README.md`.

- [ ] **Step 5: Commit**

```bash
git add apps/api/tests/test_acceptance_flow.py README.md
git commit -m "test(api): cover urgent CRM workflow end to end"
```

## Deferred Scope

The following belongs to later team integration and is intentionally excluded from this backend slice:

- production LLM provider implementation;
- React/Next.js final user interface;
- operator visual interface;
- semantic Incident Radar clustering;
- authentication and organization management;
- production PostgreSQL deployment.

The current interfaces leave explicit extension points for these components.
