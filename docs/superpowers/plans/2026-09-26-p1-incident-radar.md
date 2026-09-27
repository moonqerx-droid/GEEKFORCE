# Incident Radar P1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Детерминированно объединять похожие обращения в массовый инцидент, останавливать повторную диагностику для новых совпадений и позволять оператору одним идемпотентным действием уведомить всех связанных пользователей.

**Architecture:** `IncidentDetector` строит объяснимый weighted-Jaccard fingerprint без LLM, а `IncidentService` оркестрирует кластеризацию и рассылку через отдельный repository. `Conversation.incident_id` остаётся единственной связью членства; новые `Incident` и `IncidentUpdate` хранят состояние кластера и историю рассылок. Интеграция выполняется в двух транзакционных точках `TriageDialogueService`: после первичного анализа и после эскалации.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16, SQLite test fixtures, Pydantic 2, pytest, React 19, TypeScript 6, Vite 8, Vitest, Testing Library, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-09-26-incident-radar-design.md`

## Global Constraints

- Детектор не использует LLM, embeddings, внешнюю сеть, background worker или message broker.
- PostgreSQL 16 является runtime-хранилищем Docker; SQLite остаётся обязательным быстрым тестовым режимом.
- Существующие conversation endpoints, enum-значения и `ConversationRead.incident_id` не меняются.
- `Conversation.incident_id` остаётся nullable string без перестройки legacy-таблицы для foreign key.
- Неопределённый сервис и `security_incident` никогда не кластеризуются.
- Порог по умолчанию: `INCIDENT_SIMILARITY_THRESHOLD=0.55`; минимум кластера: `INCIDENT_MIN_CLUSTER_SIZE=3`.
- Любое изменение incident membership, broadcast и пользовательских сообщений выполняется одной транзакцией.
- Operator authentication остаётся за пределами P1; endpoints предназначены для локального демо.
- Изменения frontend другого участника в `Header.*`, `index.html` и `public/brand/**` не перезаписывать.

## Review Focus

- Два разных сервиса с одинаковым текстом ошибки не должны объединяться — закреплено unit-тестом Task 2.
- Пограничный score ровно `0.55` должен считаться совпадением, а `0.5499` — нет — закреплено unit-тестом Task 2.
- Повторное наблюдение одной conversation не должно увеличивать размер кластера — закреплено service-тестом Task 3.
- Повтор `request_key` не должен дублировать update и сообщения — закреплено API-тестом Task 5.
- Ошибка рассылки в середине списка не должна оставлять частично записанные сообщения — закреплено rollback-тестом Task 5.

---

### Task 1: Схема Incident, миграция и HTTP-контракты

**Files:**
- Create: `apps/api/app/models/incident.py`
- Create: `apps/api/app/schemas/incident.py`
- Create: `apps/api/alembic/versions/20260927_0005_incident_radar.py`
- Modify: `apps/api/app/models/__init__.py`
- Modify: `apps/api/app/core/config.py`
- Modify: `apps/api/tests/test_config.py`
- Modify: `apps/api/tests/test_migrations.py`
- Create: `apps/api/tests/test_incident_schemas.py`

**Interfaces:**
- Consumes: existing `Conversation.incident_id: str | None`, `revision` conventions and Alembic head `20260926_0004`.
- Produces: `Incident`, `IncidentUpdate`, `IncidentStatus`, `IncidentRead`, `IncidentBroadcastCreate`, `IncidentBroadcastResult`; settings `incident_similarity_threshold: float`, `incident_min_cluster_size: int`.

- [ ] **Step 1: Write failing schema/config tests**

```python
def test_incident_settings_have_safe_defaults():
    settings = Settings(_env_file=None)
    assert settings.incident_similarity_threshold == 0.55
    assert settings.incident_min_cluster_size == 3


def test_broadcast_contract_trims_and_rejects_blank_message():
    payload = IncidentBroadcastCreate(
        message="  CRM недоступна, команда работает над восстановлением.  ",
        request_key="demo-update-1",
        expected_revision=2,
    )
    assert payload.message == "CRM недоступна, команда работает над восстановлением."
    with pytest.raises(ValidationError):
        IncidentBroadcastCreate(message="   ", request_key="x", expected_revision=1)
```

- [ ] **Step 2: Write a failing migration roundtrip test**

```python
def test_incident_radar_migration_roundtrip(tmp_path):
    url = f"sqlite:///{tmp_path / 'incident.db'}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "20260926_0004")
    engine = create_engine(url)
    command.upgrade(config, "head")
    assert {"incidents", "incident_updates"} <= set(inspect(engine).get_table_names())
    command.downgrade(config, "20260926_0004")
    assert {"incidents", "incident_updates"}.isdisjoint(inspect(engine).get_table_names())
```

- [ ] **Step 3: Run tests and confirm missing contracts**

Run: `cd apps/api && ../../.venv/bin/pytest tests/test_config.py tests/test_incident_schemas.py tests/test_migrations.py -v`

Expected: FAIL on missing incident models/settings and Alembic revision.

- [ ] **Step 4: Add strict models and schemas**

Implement `Incident` with UUID-string `id`, `status`, normalized `service`, `title`, JSON `signature_tokens`, float `similarity_threshold`, integer `revision`, timestamps and `updates` relationship. Implement `IncidentUpdate` with a unique constraint on `(incident_id, request_key)` and cascade delete. Use `__mapper_args__ = {"version_id_col": revision}`.

```python
class IncidentStatus(StrEnum):
    CANDIDATE = "CANDIDATE"
    ACTIVE = "ACTIVE"
    RESOLVED = "RESOLVED"


class IncidentBroadcastCreate(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    request_key: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9._:-]+$")
    expected_revision: int = Field(ge=1)

    @field_validator("message")
    @classmethod
    def trim_message(cls, value: str) -> str:
        if not (trimmed := value.strip()):
            raise ValueError("message must not be blank")
        return trimmed
```

`IncidentRead` includes `id`, `status`, `service`, `title`, `signature_tokens`, `similarity_threshold`, `revision`, timestamps, `conversation_count`, `conversation_ids`, `evidence_tokens`, and `latest_update`. `IncidentBroadcastResult` contains `incident: IncidentRead` and `delivered_to: list[str]`.

- [ ] **Step 5: Add configuration and migration**

Add constrained settings:

```python
incident_similarity_threshold: float = Field(default=0.55, ge=0.0, le=1.0)
incident_min_cluster_size: int = Field(default=3, ge=2, le=20)
```

Migration `20260927_0005` creates `incidents` and `incident_updates`, indexes `(status, service)` and `incident_updates.incident_id`, and the unique idempotency constraint. Its downgrade drops only those new tables and indexes.

- [ ] **Step 6: Verify and commit**

Run: `cd apps/api && ../../.venv/bin/pytest tests/test_config.py tests/test_incident_schemas.py tests/test_migrations.py -v`

Expected: PASS, including PostgreSQL-compatible offline SQL generation.

```bash
git add apps/api/app/models apps/api/app/schemas apps/api/app/core/config.py apps/api/alembic apps/api/tests
git commit -m "feat(incidents): add radar persistence contracts"
```

### Task 2: Детерминированный fingerprint и weighted similarity

**Files:**
- Create: `apps/api/app/services/incident_detection.py`
- Create: `apps/api/tests/test_incident_detection.py`

**Interfaces:**
- Consumes: conversation fields `service`, `summary`, `symptoms`, `known_facts.error_text`, first user message and `playbook_id`.
- Produces: `IncidentFingerprint(service: str, weighted_tokens: dict[str, int])`, `build_fingerprint(conversation)`, `similarity(left, right) -> SimilarityResult(score, evidence_tokens)`, `recompute_signature(fingerprints)`.

- [ ] **Step 1: Write failing normalization and exclusion tests**

```python
from types import SimpleNamespace


def conversation(**overrides):
    values = {
        "service": "CRM",
        "summary": "Ошибка доступа в CRM",
        "symptoms": ["Сервис не открывается"],
        "known_facts": {"error_text": "HTTP 502"},
        "playbook_id": "service_unavailable",
        "messages": [SimpleNamespace(role="user", content="У всех не работает CRM")],
    }
    return SimpleNamespace(**(values | overrides))


def fingerprint(service, tokens):
    return IncidentFingerprint(service=service, weighted_tokens=tokens)


def test_fingerprint_normalizes_russian_and_preserves_codes():
    item = conversation(
        service="CRM", summary="Ошибка доступа в CRM", symptoms=["Сервис не открывается"],
        known_facts={"error_text": "HTTP 502"}, original="У всех не работает CRM",
    )
    result = build_fingerprint(item)
    assert result.service == "crm"
    assert "502" in result.weighted_tokens
    assert "crm" in result.weighted_tokens
    assert "не" not in result.weighted_tokens


@pytest.mark.parametrize("service,playbook", [("Не определён", "unknown"), ("ИБ", "security_incident")])
def test_unknown_and_security_are_not_clusterable(service, playbook):
    assert build_fingerprint(conversation(service=service, playbook_id=playbook)) is None
```

- [ ] **Step 2: Write failing similarity boundary tests**

```python
def test_same_text_from_different_services_never_matches():
    crm = fingerprint("crm", {"502": 3, "недоступен": 2})
    mail = fingerprint("почта", {"502": 3, "недоступен": 2})
    assert similarity(crm, mail).score == 0.0


def test_threshold_boundary_is_inclusive():
    left = fingerprint("crm", {"crm": 3, "502": 3, "вход": 2})
    exact = fingerprint("crm", {"crm": 3, "502": 3, "портал": 2})
    result = similarity(left, exact)
    assert result.score == pytest.approx(0.6)
    assert result.score >= 0.55
```

- [ ] **Step 3: Run and confirm missing detector**

Run: `cd apps/api && ../../.venv/bin/pytest tests/test_incident_detection.py -v`

Expected: FAIL because `incident_detection` does not exist.

- [ ] **Step 4: Implement deterministic scoring**

Use `TOKEN_RE = re.compile(r"[a-zа-яё0-9]+", re.IGNORECASE)`, `casefold()`, `ё -> е`, a fixed Russian/English stop-word frozenset and discard one-character tokens. Weights are service/error-code `3`, summary/symptom `2`, request-only `1`. Weighted Jaccard is:

```python
intersection = sum(min(left.get(token, 0), right.get(token, 0)) for token in universe)
union = sum(max(left.get(token, 0), right.get(token, 0)) for token in universe)
score = intersection / union if union else 0.0
```

`evidence_tokens` is the stable sorted intersection by `(-shared_weight, token)`. `recompute_signature` keeps service/error-code tokens plus tokens present in at least `ceil(member_count / 2)` fingerprints.

- [ ] **Step 5: Verify determinism and commit**

Run: `cd apps/api && ../../.venv/bin/pytest tests/test_incident_detection.py -v`

Expected: all cases pass identically over ten repeated calls.

```bash
git add apps/api/app/services/incident_detection.py apps/api/tests/test_incident_detection.py
git commit -m "feat(incidents): add deterministic similarity detector"
```

### Task 3: Repository and automatic candidate creation after escalation

**Files:**
- Create: `apps/api/app/repositories/incidents.py`
- Create: `apps/api/app/services/incidents.py`
- Modify: `apps/api/app/services/triage.py`
- Modify: `apps/api/tests/conftest.py`
- Create: `apps/api/tests/test_incident_clustering.py`

**Interfaces:**
- Consumes: Task 1 models, Task 2 detector, `ConversationRepository`, and escalated conversations.
- Produces: `IncidentRepository`, `IncidentService.observe_escalated(conversation_id: str) -> Incident | None`, and atomic cluster membership.

- [ ] **Step 1: Write failing three-request clustering tests**

Place the reusable fixtures below in `apps/api/tests/conftest.py`; keep the assertions in `test_incident_clustering.py`.

```python
@pytest.fixture
def crm_failure_factory(db_session):
    def create(code="502"):
        item = Conversation(
            workflow_version="triage-v1",
            status="ESCALATED",
            service="CRM",
            summary="CRM недоступна",
            symptoms=["не открывается"],
            known_facts={"error_text": code},
            playbook_id="service_unavailable",
        )
        item.messages.append(Message(role="user", content=f"CRM не работает, ошибка {code}"))
        db_session.add(item)
        db_session.flush()
        return item
    return create


@pytest.fixture
def mail_failure_factory(db_session):
    def create(code="502"):
        item = Conversation(
            workflow_version="triage-v1",
            status="ESCALATED",
            service="Корпоративная почта",
            summary="Почта недоступна",
            symptoms=["не открывается"],
            known_facts={"error_text": code},
            playbook_id="email_outlook",
        )
        item.messages.append(Message(role="user", content=f"Почта не работает, ошибка {code}"))
        db_session.add(item)
        db_session.flush()
        return item
    return create


@pytest.fixture
def incident_service(db_session):
    return IncidentService(
        IncidentRepository(db_session),
        threshold=0.55,
        min_cluster_size=3,
    )


@pytest.fixture
def candidate(db_session, incident_service, crm_failure_factory):
    created = None
    for _ in range(3):
        item = crm_failure_factory(code="502")
        created = incident_service.observe_escalated(item.id) or created
    assert created is not None
    db_session.flush()
    return created


@pytest.fixture
def seeded_crm_candidate(candidate):
    return candidate


def test_three_similar_escalations_form_one_candidate(db_session, incident_service, crm_failure_factory):
    conversations = [crm_failure_factory(code="502") for _ in range(3)]
    results = [incident_service.observe_escalated(item.id) for item in conversations]
    incident = next(result for result in results if result is not None)
    assert incident.status == "CANDIDATE"
    assert incident.service == "crm"
    db_session.flush()
    for item in conversations:
        db_session.refresh(item)
    assert {item.incident_id for item in conversations} == {incident.id}
    assert set(IncidentRepository(db_session).conversation_ids(incident.id)) == {item.id for item in conversations}


def test_reobserving_member_does_not_duplicate_membership(incident_service, candidate):
    before = incident_service.read(candidate.id).conversation_ids
    incident_service.observe_escalated(before[0])
    assert incident_service.read(candidate.id).conversation_ids == before
```

- [ ] **Step 2: Add unrelated-service, race and rollback tests**

```python
def test_different_service_does_not_complete_cluster(incident_service, crm_failure_factory, mail_failure_factory):
    for item in (crm_failure_factory(), crm_failure_factory(), mail_failure_factory()):
        incident_service.observe_escalated(item.id)
    assert incident_service.repository.list_open("crm") == []
    assert incident_service.repository.list_open("корпоративная почта") == []


def test_cluster_create_race_rereads_once(db_session, incident_service, crm_failure_factory, monkeypatch):
    members = [crm_failure_factory() for _ in range(3)]
    original = incident_service.repository.create_candidate
    calls = 0
    def lose_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            competing = original(*args, **kwargs)
            db_session.flush()
            raise IntegrityError("duplicate candidate", {}, None)
        return original(*args, **kwargs)
    monkeypatch.setattr(incident_service.repository, "create_candidate", lose_once)
    result = incident_service.observe_escalated(members[-1].id)
    assert result is not None
    assert len(incident_service.list_open()) == 1


def test_signature_failure_rolls_back_membership(db_session, incident_service, crm_failure_factory, monkeypatch):
    members = [crm_failure_factory() for _ in range(3)]
    monkeypatch.setattr(incident_service, "_recompute_signature", lambda *_: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError, match="boom"):
        incident_service.observe_escalated(members[-1].id)
    db_session.rollback()
    assert all(ConversationRepository(db_session).get(item.id).incident_id is None for item in members)
```

- [ ] **Step 3: Run and confirm missing repository/service**

Run: `cd apps/api && ../../.venv/bin/pytest tests/test_incident_clustering.py -v`

Expected: FAIL on missing `IncidentRepository` and `IncidentService`.

- [ ] **Step 4: Implement repository and service boundaries**

Repository methods:

```python
list_open(service: str) -> list[Incident]
list_unlinked_escalated(service: str, exclude_id: str) -> list[Conversation]
conversation_ids(incident_id: str) -> list[str]
link(conversation: Conversation, incident: Incident) -> None
create_candidate(service: str, title: str, signature_tokens: list[str], threshold: float) -> Incident
get(incident_id: str) -> Incident | None
```

`observe_escalated` first tries the best open incident by score and stable ID tie-break. If none qualifies, compare unlinked escalated conversations; current plus matching candidates must reach `incident_min_cluster_size`. Create and link in the caller's existing session without committing. Emit structured log event names from the spec.

Catch a candidate-create `IntegrityError` once, roll back its savepoint, re-read open incidents of the same service and retry only membership against the best qualifying incident. A second conflict returns no membership and logs `incident.detection_failed`.

- [ ] **Step 5: Integrate the escalation transaction**

Inject `IncidentService` into `TriageDialogueService`. At the end of `_escalate`, after status/card/message fields are prepared and before `_commit`, call `observe_escalated`. Catch detector exceptions, rollback only radar changes using `session.begin_nested()`, log `incident.detection_failed`, and preserve the support turn.

- [ ] **Step 6: Verify and commit**

Run: `cd apps/api && ../../.venv/bin/pytest tests/test_incident_clustering.py tests/test_triage_integration.py -v`

Expected: one candidate for three similar CRM requests, no duplicates, normal dialogue regression tests green.

```bash
git add apps/api/app/repositories/incidents.py apps/api/app/services/incidents.py apps/api/app/services/triage.py apps/api/tests
git commit -m "feat(incidents): cluster escalated conversations"
```

### Task 4: First-turn join and user notification

**Files:**
- Modify: `apps/api/app/services/incidents.py`
- Modify: `apps/api/app/services/triage.py`
- Modify: `apps/api/tests/test_incident_clustering.py`
- Modify: `apps/api/tests/test_triage_integration.py`

**Interfaces:**
- Consumes: an existing `CANDIDATE|ACTIVE` incident and populated first-turn analysis fields.
- Produces: `IncidentMatch(incident_id: str, score: float, evidence_tokens: list[str])`; `IncidentService.match_first_turn(conversation_id: str) -> IncidentMatch | None`; immediate `ESCALATED` response with `incident_id` and no troubleshooting question.

- [ ] **Step 1: Write the failing fourth-request integration test**

```python
def test_fourth_matching_request_joins_before_diagnostics(client, seeded_crm_candidate):
    cid = client.post("/api/conversations").json()["id"]
    state = send(client, cid, "CRM не открывается, у меня ошибка 502")
    assert state["status"] == "ESCALATED"
    assert state["incident_id"] == seeded_crm_candidate.id
    assert state["completed_steps"] == []
    assert len([m for m in state["messages"] if m["role"] == "assistant"]) == 1
    assert "массов" in state["messages"][-1]["content"].casefold()
```

- [ ] **Step 2: Write failure-is-advisory test**

Monkeypatch `match_first_turn` to raise `RuntimeError`; assert the first message still returns `200`, stays in normal `CLARIFYING|TROUBLESHOOTING|ESCALATED` flow selected by triage, and has `incident_id is None`.

- [ ] **Step 3: Run and confirm normal diagnostics still start**

Run: `cd apps/api && ../../.venv/bin/pytest tests/test_triage_integration.py -k 'fourth_matching or radar_failure' -v`

Expected: FAIL because the fourth request receives the ordinary question.

- [ ] **Step 4: Implement the first-turn hook**

In the `previous_status == "NEW"` branch, assign analysis fields, then call `match_first_turn` before `analysis.should_escalate` and `_advance`. On match:

```python
conversation.incident_id = match.incident_id
conversation.status = "ESCALATED"
conversation.current_step_code = None
conversation.current_step_instruction = None
conversation.escalation_card = self.engine.build_escalation_card(
    self._context(conversation), "обращение совпало с возможным массовым инцидентом"
).model_dump(mode="json")
self._message(
    conversation,
    "assistant",
    "Похоже, проблема массовая. Команда поддержки уже расследует инцидент; обновления появятся в этом обращении.",
)
return self._commit(conversation)
```

Do not append the unused playbook question. Recompute the incident signature after linking.

- [ ] **Step 5: Verify and commit**

Run: `cd apps/api && ../../.venv/bin/pytest tests/test_incident_clustering.py tests/test_triage_integration.py -v`

Expected: fourth request links atomically; unrelated and detector-error requests keep normal flow.

```bash
git add apps/api/app/services apps/api/tests
git commit -m "feat(dialogue): join active incidents on first turn"
```

### Task 5: Operator list and idempotent broadcast API

**Files:**
- Modify: `apps/api/app/api/routes/operator.py`
- Modify: `apps/api/app/repositories/incidents.py`
- Modify: `apps/api/app/services/incidents.py`
- Modify: `apps/api/tests/conftest.py`
- Create: `apps/api/tests/test_incident_api.py`

**Interfaces:**
- Consumes: Task 1 HTTP schemas and Task 3 membership.
- Produces: `GET /api/operator/incidents`, `POST /api/operator/incidents/{incident_id}/broadcast`.

- [ ] **Step 1: Write failing list ordering test**

```python
@pytest.fixture
def incident_factory(db_session):
    def create(status="CANDIDATE", members=3):
        incident = Incident(
            status=status,
            service="crm",
            title=f"CRM {status}",
            signature_tokens=["crm", "502"],
            similarity_threshold=0.55,
        )
        db_session.add(incident)
        db_session.flush()
        for index in range(members):
            conversation = Conversation(
                workflow_version="triage-v1",
                status="ESCALATED",
                service="CRM",
                incident_id=incident.id,
                summary=f"CRM failure {index}",
            )
            db_session.add(conversation)
        db_session.flush()
        return incident
    return create


@pytest.fixture
def resolved_incident(incident_factory):
    return incident_factory(status="RESOLVED", members=3)


def test_incident_list_orders_open_clusters(client, incident_factory):
    resolved = incident_factory(status="RESOLVED", members=5)
    active = incident_factory(status="ACTIVE", members=4)
    small = incident_factory(status="CANDIDATE", members=2)
    large = incident_factory(status="CANDIDATE", members=3)
    result = client.get("/api/operator/incidents").json()
    assert [item["id"] for item in result] == [large.id, small.id, active.id]
    with_resolved = client.get("/api/operator/incidents?include_resolved=true").json()
    assert {item["id"] for item in with_resolved} == {resolved.id, active.id, small.id, large.id}
```

- [ ] **Step 2: Write failing idempotent broadcast test**

```python
def test_broadcast_reaches_every_member_once(client, candidate):
    payload = {
        "message": "CRM недоступна. Команда уже восстанавливает сервис.",
        "request_key": "demo-update-1",
        "expected_revision": candidate.revision,
    }
    first = client.post(f"/api/operator/incidents/{candidate.id}/broadcast", json=payload)
    assert first.status_code == 200
    replay = client.post(f"/api/operator/incidents/{candidate.id}/broadcast", json=payload)
    assert replay.status_code == 200
    assert replay.json()["delivered_to"] == first.json()["delivered_to"]
    for cid in first.json()["delivered_to"]:
        state = client.get(f"/api/conversations/{cid}").json()
        assert [m["content"] for m in state["messages"]].count(payload["message"]) == 1
```

- [ ] **Step 3: Add stale, resolved and rollback tests**

```python
def test_broadcast_rejects_stale_and_resolved(client, candidate, resolved_incident):
    stale = {"message": "Обновление", "request_key": "stale-1", "expected_revision": candidate.revision - 1}
    assert client.post(f"/api/operator/incidents/{candidate.id}/broadcast", json=stale).status_code == 409
    closed = {"message": "Обновление", "request_key": "closed-1", "expected_revision": resolved_incident.revision}
    assert client.post(f"/api/operator/incidents/{resolved_incident.id}/broadcast", json=closed).status_code == 409


def test_broadcast_rolls_back_partial_delivery(db_session, incident_service, candidate, monkeypatch):
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
        incident_service.broadcast(candidate.id, "Обновление", "rollback-1", candidate.revision)
    db_session.rollback()
    assert incident_service.repository.find_update(candidate.id, "rollback-1") is None
    assert all("Обновление" not in [m.content for m in ConversationRepository(db_session).get(cid).messages]
               for cid in incident_service.repository.conversation_ids(candidate.id))
```

- [ ] **Step 4: Run focused API tests**

Run: `cd apps/api && ../../.venv/bin/pytest tests/test_incident_api.py -v`

Expected: FAIL with route `404`.

- [ ] **Step 5: Implement transactional broadcast**

`IncidentService.broadcast` validates revision/status, checks `(incident_id, request_key)` before mutation, appends an assistant `Message` to every linked conversation, touches `updated_at` so each conversation revision advances, creates `IncidentUpdate`, changes `CANDIDATE` to `ACTIVE`, and commits once. Map domain `IncidentNotFound` to `404` and `IncidentConflict` to `409` in the thin route.

- [ ] **Step 6: Verify and commit**

Run: `cd apps/api && ../../.venv/bin/pytest tests/test_incident_api.py tests/test_triage_integration.py -v`

Expected: list and broadcast contracts pass; repeated request key creates no duplicates.

```bash
git add apps/api/app/api/routes/operator.py apps/api/app/repositories/incidents.py apps/api/app/services/incidents.py apps/api/tests
git commit -m "feat(api): expose incident radar and broadcast"
```

### Task 6: Production React operator controls

**Files:**
- Modify: `apps/web/src/api/types.ts`
- Modify: `apps/web/src/api/client.ts`
- Modify: `apps/web/src/test/fixtures.ts`
- Modify: `apps/web/src/features/operator/useOperatorTickets.ts`
- Modify: `apps/web/src/features/operator/IncidentsSection.tsx`
- Modify: `apps/web/src/features/operator/IncidentsSection.css`
- Modify: `apps/web/src/features/operator/OperatorPage.tsx`
- Create: `apps/web/src/features/operator/IncidentsSection.test.tsx`
- Modify: `apps/web/src/features/operator/OperatorPage.test.tsx`
- Modify: `apps/api/app/templates/operator-debug.html`
- Modify: `apps/api/app/static/operator-debug.js`
- Modify: `apps/api/app/static/debug.css`
- Modify: `apps/api/tests/test_debug_page.py`

**Interfaces:**
- Consumes: Task 5 `IncidentRead`, `IncidentBroadcastCreate`, `IncidentBroadcastResult` JSON.
- Produces: typed `api.listIncidents()` and `api.broadcastIncident()` plus operator candidate/active cards and broadcast form.

- [ ] **Step 1: Write failing component tests**

```tsx
it("shows evidence and broadcasts with the current revision", async () => {
  const onBroadcast = vi.fn().mockResolvedValue(undefined);
  render(<IncidentsSection incidents={[makeIncident()]} onBroadcast={onBroadcast} />);
  expect(screen.getByText("502")).toBeInTheDocument();
  await userEvent.type(screen.getByLabelText("Обновление для пользователей"), "CRM восстанавливается");
  await userEvent.click(screen.getByRole("button", { name: "Отправить всем" }));
  expect(onBroadcast).toHaveBeenCalledWith("incident-1", {
    message: "CRM восстанавливается",
    request_key: expect.any(String),
    expected_revision: 1,
  });
});
```

```tsx
it("keeps blank broadcast disabled and reports a failed submit", async () => {
  const onBroadcast = vi.fn().mockRejectedValue(new Error("network"));
  render(<IncidentsSection incidents={[makeIncident({ status: "ACTIVE" })]} onBroadcast={onBroadcast} />);
  const button = screen.getByRole("button", { name: "Отправить всем" });
  expect(button).toBeDisabled();
  await userEvent.type(screen.getByLabelText("Обновление для пользователей"), "Статус без изменений");
  await userEvent.click(button);
  expect(await screen.findByRole("alert")).toHaveTextContent("Не удалось отправить обновление");
  expect(screen.getByText("Активный")).toBeInTheDocument();
  expect(screen.getByText(/Связанных обращений: 3/)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run focused frontend tests**

Run: `cd apps/web && npm test -- --run src/features/operator/IncidentsSection.test.tsx src/features/operator/OperatorPage.test.tsx`

Expected: FAIL because types, callback and form do not exist.

- [ ] **Step 3: Add exact TypeScript contracts and client call**

```typescript
export interface Incident {
  id: string;
  status: "CANDIDATE" | "ACTIVE" | "RESOLVED";
  service: string;
  title: string;
  signature_tokens: string[];
  evidence_tokens: string[];
  similarity_threshold: number;
  revision: number;
  conversation_count: number;
  conversation_ids: string[];
  latest_update: { message: string; created_at: string } | null;
  created_at: string;
  updated_at: string;
}
```

`broadcastIncident(id, payload, signal)` posts to `/api/operator/incidents/${id}/broadcast`. Generate `request_key` once per button action with `crypto.randomUUID()`; reuse it only for an explicit retry of that same UI action.

Add this fixture factory to `apps/web/src/test/fixtures.ts`:

```typescript
export function makeIncident(overrides: Partial<Incident> = {}): Incident {
  return {
    id: "incident-1",
    status: "CANDIDATE",
    service: "crm",
    title: "Массовая недоступность CRM",
    signature_tokens: ["crm", "502"],
    evidence_tokens: ["502"],
    similarity_threshold: 0.55,
    revision: 1,
    conversation_count: 3,
    conversation_ids: ["c1", "c2", "c3"],
    latest_update: null,
    created_at: "2026-09-27T08:00:00Z",
    updated_at: "2026-09-27T08:00:00Z",
    ...overrides,
  };
}
```

- [ ] **Step 4: Implement accessible operator interaction**

Render status badge, service/title, count, evidence token chips, latest update, labelled textarea and `Отправить всем` button. Keep per-incident pending/error state so one broadcast does not disable all cards. On success replace the incident with the returned `incident`; do not optimistically append a message before the API response.

- [ ] **Step 5: Add debug operator controls**

Before the final frontend run, extend `/debug/operator` with the same read-only incident cards and broadcast form. Its JavaScript must call only `GET /api/operator/incidents` and `POST /api/operator/incidents/{id}/broadcast`, keep `request_key` stable while retrying a failed submit, and refresh both incidents and tickets after success. Add an API template test:

```python
def test_operator_debug_exposes_incident_radar_controls(client):
    page = client.get("/debug/operator")
    assert page.status_code == 200
    assert 'aria-label="Массовые инциденты"' in page.text
    assert 'id="incident-radar"' in page.text
```

Run: `cd apps/api && ../../.venv/bin/pytest tests/test_debug_page.py -v`

Expected: debug page renders the Radar container and the versioned operator script.

- [ ] **Step 6: Verify and commit**

Run: `cd apps/web && npm test -- --run && npm run lint && npm run build`

Expected: all tests/build pass; lint has no new errors or warnings.

```bash
git add apps/web/src/api apps/web/src/test apps/web/src/features/operator apps/api/app/templates/operator-debug.html apps/api/app/static apps/api/tests/test_debug_page.py
git commit -m "feat(operator): add incident broadcast controls"
```

### Task 7: Four-request demo seed, acceptance and cross-platform smoke

**Files:**
- Create: `apps/api/tests/test_incident_acceptance.py`
- Create: `scripts/seed-incident-demo.py`
- Modify: `scripts/smoke-p0.sh`
- Modify: `scripts/smoke-p0.ps1`
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `.github/workflows/backend.yml`

**Interfaces:**
- Consumes: all P1 endpoints and existing conversation API.
- Produces: reproducible three-seed-plus-fourth-request demo in pytest, macOS/Linux and Windows.

- [ ] **Step 1: Write the failing acceptance test**

```python
def send(client, cid, content):
    response = client.post(f"/api/conversations/{cid}/messages", json={"content": content})
    assert response.status_code == 200, response.text
    return response.json()


def create_conversation_with_message(client, text):
    cid = client.post("/api/conversations").json()["id"]
    return send(client, cid, text)


def create_escalated_crm(client, text):
    state = create_conversation_with_message(client, text)
    while state["status"] == "CLARIFYING":
        state = send(client, state["id"], "ошибка 502, у коллег тоже")
    while state["status"] == "TROUBLESHOOTING":
        response = client.post(
            f"/api/conversations/{state['id']}/step-result",
            json={"outcome": "not_helped"},
        )
        assert response.status_code == 200, response.text
        state = response.json()
    assert state["status"] == "ESCALATED"
    return state["id"]


def test_fourth_crm_failure_joins_and_receives_broadcast(client):
    seeded_ids = [create_escalated_crm(client, text) for text in (
        "CRM не открывается, ошибка 502",
        "При входе в CRM получаю 502",
        "Корпоративная CRM недоступна: HTTP 502",
    )]
    incidents = client.get("/api/operator/incidents").json()
    assert len(incidents) == 1
    incident = incidents[0]
    assert set(incident["conversation_ids"]) == set(seeded_ids)

    fourth = create_conversation_with_message(client, "Снова 502 при открытии CRM")
    assert fourth["status"] == "ESCALATED"
    assert fourth["incident_id"] == incident["id"]

    incident = client.get("/api/operator/incidents").json()[0]
    payload = {"message": "Восстанавливаем CRM", "request_key": "acceptance-1", "expected_revision": incident["revision"]}
    delivered = client.post(f"/api/operator/incidents/{incident['id']}/broadcast", json=payload).json()["delivered_to"]
    assert set(delivered) == {*seeded_ids, fourth["id"]}
    for cid in delivered:
        assert client.get(f"/api/conversations/{cid}").json()["messages"][-1]["content"] == payload["message"]
```

- [ ] **Step 2: Run acceptance and fix only contract mismatches**

Run: `cd apps/api && ../../.venv/bin/pytest tests/test_incident_acceptance.py -v`

Expected: one candidate, fourth request short-circuited, one update delivered to all four.

- [ ] **Step 3: Add deterministic seed command**

`scripts/seed-incident-demo.py --base-url http://localhost:8000` uses only Python stdlib `urllib.request`, creates the three seed conversations, drives them to escalation, prints incident ID and exits non-zero unless exactly one candidate contains all three IDs. It never deletes existing data; README instructs using a fresh local database for a deterministic demo.

- [ ] **Step 4: Extend both smoke scripts**

After the existing P0 check, seed three CRM requests, send the fourth, list incidents, broadcast `Демо: команда восстанавливает CRM`, and assert all four retrieved conversations end with that exact assistant message. Shell uses `curl` plus Python JSON parsing; PowerShell uses `Invoke-RestMethod`. Neither script calls `docker compose down` or deletes the volume.

- [ ] **Step 5: Document demo and CI**

Add `INCIDENT_SIMILARITY_THRESHOLD=0.55` and `INCIDENT_MIN_CLUSTER_SIZE=3` to `.env.example` and Compose API environment. README gets exact root-directory commands for rules and Ollama modes plus the four-request demo. Backend CI runs `test_incident_acceptance.py` and the real PostgreSQL migration smoke.

- [ ] **Step 6: Run full verification**

```bash
cd apps/api && ../../.venv/bin/pytest -q
cd ../.. && PYTHONPATH=services/ai .venv/bin/pytest services/ai/tests -q
cd apps/web && npm test -- --run && npm run lint && npm run build
cd ../.. && docker compose up -d --build
./scripts/smoke-p0.sh
```

Expected: all suites pass; PostgreSQL healthy; P0 and four-request Incident Radar smoke complete without network AI dependency in `AI_PROVIDER=rules` mode.

- [ ] **Step 7: Commit**

```bash
git add apps/api/tests/test_incident_acceptance.py scripts .env.example docker-compose.yml README.md .github/workflows/backend.yml
git commit -m "test(incidents): verify four-request radar demo"
```

### Task 8: Whole-branch review and demo handoff

**Files:**
- Modify: `PROJECT_PLAN.md`
- Create: `docs/incident-radar-demo.md`

**Interfaces:**
- Consumes: green P1 branch and all Task 1–7 contracts.
- Produces: verified counts, demo script, rollback notes and merge-ready review package.

- [ ] **Step 1: Record exact verified status**

Run every command from Task 7, record exact pass/skip counts and current commit SHA. Do not claim Windows execution unless `smoke-p0.ps1` actually ran on Windows; record syntax/static validation separately.

- [ ] **Step 2: Create the four-minute demo sequence**

`docs/incident-radar-demo.md` contains exact messages, expected screen states, operator broadcast text, fallback steps if Ollama is unavailable, and a 30-second recovery path using `AI_PROVIDER=rules` plus `docker compose up -d --build`.

- [ ] **Step 3: Run hygiene and fresh review**

```bash
git status --short
git diff --check origin/develop HEAD
git log --oneline origin/develop..HEAD
```

Generate the executing-plans review package, dispatch one fresh whole-branch reviewer, fix Critical/Important findings by RED→GREEN tests, and ledger deferred Minor findings.

- [ ] **Step 4: Commit documentation**

```bash
git add PROJECT_PLAN.md docs/incident-radar-demo.md
git commit -m "docs: record Incident Radar demo readiness"
```
