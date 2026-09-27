# Managed Users, Profiles, Metrics and Safe RAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship administrator-managed accounts, specialist profiles and metrics, uploadable company knowledge, and a faster three-tier Ollama answer path with fail-closed corporate claims.

**Architecture:** Extend the existing FastAPI/SQLAlchemy role model rather than replacing authentication. Keep account administration, metrics, document ingestion, retrieval, and answer policy as focused services with explicit schemas; the React client consumes those APIs through typed feature modules. Existing deterministic playbooks remain the safety controller, while one bounded Ollama call may produce either evidence-backed company answers or clearly labelled low-risk general guidance.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL/SQLite tests, Pydantic 2, PyPDF and python-docx, React 19, TypeScript 6, Vitest, Testing Library, Ollama Qwen 3.5.

**Spec:** `docs/superpowers/specs/2026-09-28-admin-rag-profiles-design.md`

## Global Constraints

- Existing roles `employee`, `operator`, `admin`, cookie sessions, PostgreSQL, and the operator chat remain compatible.
- Existing passwords remain Argon2 hashes; no current or temporary raw password is stored or audited.
- At most one synchronous Ollama call is allowed per user turn; default timeout is 20 seconds and generated output is capped near 300 tokens.
- Corporate claims require a retrieved source and exact evidence quote; unsupported high-risk questions go to an operator.
- General model guidance is allowed only for low-risk reversible technical steps and must be labelled as non-corporate guidance.
- PDF, DOCX, TXT, and Markdown are accepted; only active `READY` documents participate in retrieval.
- The frontend must work on macOS and Windows through the existing Docker workflow and remain responsive at narrow widths.

## Review Focus

- A disabled or role-changed user with an old cookie must lose access immediately; Task 1 adds an integration test for session revocation.
- Two administrators editing the same user must not silently overwrite each other; Task 1 adds revision-based conflict coverage.
- A malformed or misleading uploaded file must never become searchable; Task 4 tests MIME/extension mismatch and failed extraction.
- A model citation that points to a real chunk but quotes text not present in it must be rejected; Task 5 tests exact evidence validation.
- A company-policy question with no corporate source must not fall through to general model knowledge; Task 6 tests risk routing and escalation.

---

### Task 1: Managed accounts, temporary credentials and audit

**Files:**
- Create: `apps/api/alembic/versions/20260928_0007_managed_accounts.py`
- Create: `apps/api/app/models/audit.py`
- Create: `apps/api/app/schemas/admin_users.py`
- Create: `apps/api/app/services/user_admin.py`
- Create: `apps/api/tests/test_admin_users.py`
- Modify: `apps/api/app/models/auth.py`
- Modify: `apps/api/app/models/__init__.py`
- Modify: `apps/api/app/repositories/auth.py`
- Modify: `apps/api/app/api/routes/admin.py`
- Modify: `apps/api/app/api/dependencies/auth.py`
- Modify: `apps/api/app/schemas/auth.py`
- Modify: `apps/api/app/api/routes/auth.py`
- Modify: `apps/api/app/services/auth.py`
- Modify: `apps/api/tests/test_migrations.py`

**Interfaces:**
- Produces: `AdminUserRead`, `AdminUserCreate`, `AdminUserUpdate`, `TemporaryCredentialRead`; `UserAdminService.create_operator`, `update_user`, `reset_password`; `User.must_change_password`, `User.revision`.
- Consumes: existing `User`, `AuthSession`, `hash_password`, `new_token`, role dependencies and trusted-origin protection.

- [ ] **Step 1: Write failing migration and service tests**

```python
def test_admin_creates_operator_with_one_time_password(client, admin_override):
    response = client.post("/api/admin/users/operators", json={
        "full_name": "Анна Смирнова", "email": "anna@example.org", "department": "it",
    })
    assert response.status_code == 201
    assert response.json()["user"]["must_change_password"] is True
    assert len(response.json()["temporary_password"]) >= 14

def test_role_change_revokes_existing_sessions(db_session, user_admin_service):
    user, session = seeded_user_and_session(db_session)
    user_admin_service.update_user(user.id, {"role": "operator", "revision": 1})
    assert session.revoked_at is not None

def test_stale_user_revision_returns_conflict(client, admin_override, seeded_employee):
    response = client.patch(f"/api/admin/users/{seeded_employee.id}", json={
        "full_name": "Новое Имя", "revision": 0,
    })
    assert response.status_code == 409
```

- [ ] **Step 2: Run tests and verify RED**

Run: `cd apps/api && pytest tests/test_admin_users.py tests/test_migrations.py -q`
Expected: FAIL because managed-account schemas, columns, service, and routes do not exist.

- [ ] **Step 3: Add schema, model and service implementation**

Implement the migration with `users.must_change_password BOOLEAN NOT NULL DEFAULT false`, `users.revision INTEGER NOT NULL DEFAULT 1`, and `admin_audit_events(id, actor_id, target_user_id, action, changes, created_at)`. Implement:

```python
class UserAdminService:
    def create_operator(self, payload: AdminUserCreate, actor: User) -> tuple[User, str]: ...
    def update_user(self, user_id: str, payload: AdminUserUpdate, actor: User) -> User: ...
    def reset_password(self, user_id: str, actor: User) -> tuple[User, str]: ...
```

Generate passwords with `secrets.choice` from unambiguous upper/lower/digit characters, hash immediately, return once, set `must_change_password=True`, revoke sessions on sensitive changes, prevent self-disable and removal of the last active admin, and write redacted audit rows in the same transaction.

- [ ] **Step 4: Enforce forced password change**

Add `must_change_password` to `CurrentUser`. Add `POST /api/auth/change-password` accepting current and new password. The auth dependency permits `/me`, `/logout`, and `/change-password`, while protected role endpoints return `403 password_change_required` until the flag is cleared.

- [ ] **Step 5: Run focused and complete API tests**

Run: `cd apps/api && DATABASE_URL=sqlite:////private/tmp/helpflow-task1.db pytest tests -q --ignore=tests/test_migrations.py && env -u DATABASE_URL pytest tests/test_migrations.py -q`
Expected: all API tests pass, PostgreSQL smoke may skip when its service is absent.

- [ ] **Step 6: Commit**

```bash
git add apps/api
git commit -m "feat(admin): manage users with temporary credentials"
```

### Task 2: Specialist metrics and profile API

**Files:**
- Create: `apps/api/app/schemas/profile.py`
- Create: `apps/api/app/services/operator_metrics.py`
- Create: `apps/api/app/api/routes/profile.py`
- Create: `apps/api/tests/test_profile.py`
- Create: `apps/api/tests/test_operator_metrics.py`
- Modify: `apps/api/app/main.py`
- Modify: `apps/api/app/api/routes/admin.py`
- Modify: `apps/api/app/core/config.py`

**Interfaces:**
- Consumes: managed `User`, current-user dependency, conversation timestamps, ratings, roles.
- Produces: `OperatorMetricsService.for_operator(user_id, days)`, `/api/profile`, `/api/profile/metrics`, `/api/admin/users/{id}/metrics`.

- [ ] **Step 1: Write failing metrics tests with hand-calculated values**

```python
def test_operator_metrics_are_scoped_to_requested_operator(db_session):
    anna, oleg = seed_two_operators_with_known_conversations(db_session)
    result = OperatorMetricsService(db_session).for_operator(anna.id, 7)
    assert result.resolved == 2
    assert result.in_progress == 1
    assert result.median_first_reply_minutes == 5.0
    assert result.average_rating == 4.5

def test_operator_profile_does_not_expose_team_comparison(operator_client):
    body = operator_client.get("/api/profile/metrics?days=7").json()
    assert "operators" not in body
    assert "rank" not in body
```

- [ ] **Step 2: Run tests and verify RED**

Run: `cd apps/api && pytest tests/test_profile.py tests/test_operator_metrics.py -q`
Expected: FAIL because the profile router and metrics service are missing.

- [ ] **Step 3: Implement percentile-safe metric service and profile routes**

Use one service for both audiences. `for_operator` returns in-progress, waiting-first-reply, assigned, resolved, median/p90 first reply, median/p90 resolution, average rating, rating count, SLA rate, daily counts, topic counts, and urgency counts. `/api/profile/metrics` serializes only the personal subset; admin detail includes every field. Add `support_first_reply_sla_minutes: int = 15` to settings.

- [ ] **Step 4: Implement own-profile updates**

`PATCH /api/profile` permits only `full_name` and `department`; it never changes email, role, active status, or `must_change_password`. Return the same `CurrentUser` contract.

- [ ] **Step 5: Run focused and complete API tests**

Run: `cd apps/api && DATABASE_URL=sqlite:////private/tmp/helpflow-task2.db pytest tests -q --ignore=tests/test_migrations.py && env -u DATABASE_URL pytest tests/test_migrations.py -q`
Expected: all API tests pass.

- [ ] **Step 6: Commit**

```bash
git add apps/api
git commit -m "feat(metrics): add specialist profiles and scoped metrics"
```

### Task 3: Admin user catalog and polished profile frontend

**Files:**
- Create: `apps/web/src/features/admin/UserEditor.tsx`
- Create: `apps/web/src/features/admin/OperatorMetricsPanel.tsx`
- Create: `apps/web/src/features/admin/AdminUsers.test.tsx`
- Create: `apps/web/src/features/profile/ProfilePage.tsx`
- Create: `apps/web/src/features/profile/ProfilePage.css`
- Create: `apps/web/src/features/profile/ProfilePage.test.tsx`
- Modify: `apps/web/src/features/admin/AdminTeam.tsx`
- Modify: `apps/web/src/features/admin/Admin.css`
- Modify: `apps/web/src/api/types.ts`
- Modify: `apps/web/src/api/client.ts`
- Modify: `apps/web/src/components/Header.tsx`
- Modify: `apps/web/src/App.tsx`
- Modify: `apps/web/src/test/server.ts`

**Interfaces:**
- Consumes: Task 1 admin-user endpoints and Task 2 profile/metrics endpoints.
- Produces: typed admin catalog, one-time credential dialog, `/profile` UI and enforced-password screen.

- [ ] **Step 1: Write failing interaction tests**

```tsx
it("creates a specialist and reveals the temporary password once", async () => {
  renderAdminUsers();
  await user.click(screen.getByRole("button", { name: "Создать специалиста" }));
  await user.type(screen.getByLabelText("ФИО"), "Анна Смирнова");
  await user.type(screen.getByLabelText("Рабочая почта"), "anna@example.org");
  await user.click(screen.getByRole("button", { name: "Создать аккаунт" }));
  expect(await screen.findByText("Временный пароль")).toBeInTheDocument();
});

it("shows only personal headline metrics to a specialist", async () => {
  renderProfileAsOperator();
  expect(await screen.findByText("Мои показатели")).toBeInTheDocument();
  expect(screen.queryByText("Рейтинг команды")).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests and verify RED**

Run: `cd apps/web && npm test -- --run src/features/admin/AdminUsers.test.tsx src/features/profile/ProfilePage.test.tsx`
Expected: FAIL because the catalog and profile page do not exist.

- [ ] **Step 3: Implement typed client and admin catalog**

Replace the invitation form with `full_name`, email, and department. Add search/role/status filters, editable drawer, reset-password confirmation, a one-time password dialog with copy action, audit-safe error copy, and the full specialist metrics panel. Keep old invite client methods only where legacy tests require them.

- [ ] **Step 4: Implement the profile page and navigation**

Make the header avatar/name a link to `/profile`. Build an intentional two-column desktop/one-column mobile page with identity header, personal metrics, editable details, and password security card. When `must_change_password` is true, route guards send the user to `/profile?change-password=required` and disable navigation elsewhere.

- [ ] **Step 5: Verify frontend**

Run: `cd apps/web && npm test -- --run && npm run build && npm run lint`
Expected: tests, build, and lint exit 0.

- [ ] **Step 6: Commit**

```bash
git add apps/web
git commit -m "feat(web): redesign user management and specialist profile"
```

### Task 4: Document ingestion and knowledge administration API

**Files:**
- Create: `apps/api/alembic/versions/20260928_0008_knowledge_documents.py`
- Create: `apps/api/app/models/knowledge.py`
- Create: `apps/api/app/schemas/knowledge.py`
- Create: `apps/api/app/services/document_extraction.py`
- Create: `apps/api/app/services/knowledge_admin.py`
- Create: `apps/api/app/api/routes/knowledge_admin.py`
- Create: `apps/api/tests/test_document_extraction.py`
- Create: `apps/api/tests/test_knowledge_admin.py`
- Modify: `apps/api/app/models/__init__.py`
- Modify: `apps/api/app/main.py`
- Modify: `apps/api/app/core/config.py`
- Modify: `apps/api/requirements.txt`
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Modify: `apps/api/tests/test_migrations.py`

**Interfaces:**
- Produces: `KnowledgeDocument`, `KnowledgeChunk`, `DocumentExtractor.extract(path, mime)`, admin document endpoints, `KnowledgeRepository.ready_chunks()`.
- Consumes: admin dependency, configured `knowledge_storage_dir`, PostgreSQL/SQLite models.

- [ ] **Step 1: Write failing extraction and lifecycle tests**

```python
@pytest.mark.parametrize((filename, payload, expected), [
    ("rules.txt", "VPN доступен только штатным сотрудникам".encode(), "VPN доступен"),
    ("rules.md", b"# VPN\nUse approved access", "Use approved access"),
])
def test_text_documents_become_ready(filename, payload, expected, knowledge_service):
    document = knowledge_service.ingest(filename, payload, "text/plain", admin_id="a")
    assert document.status == "READY"
    assert expected in document.chunks[0].text

def test_extension_mime_mismatch_is_failed(knowledge_service):
    document = knowledge_service.ingest("rules.pdf", b"not a pdf", "application/pdf", admin_id="a")
    assert document.status == "FAILED"
    assert knowledge_service.ready_chunks() == []
```

- [ ] **Step 2: Run tests and verify RED**

Run: `cd apps/api && pytest tests/test_document_extraction.py tests/test_knowledge_admin.py tests/test_migrations.py -q`
Expected: FAIL because models, extractors, migration, and endpoints are missing.

- [ ] **Step 3: Implement safe file storage and extraction**

Add `pypdf` and `python-docx`. Limit uploads to 10 MiB and PDF to 200 pages; sniff signatures before parsing; normalize Unicode and whitespace; reject empty extraction. Store by generated document id, never by user filename. Chunk at paragraph boundaries into roughly 1,200-character chunks with 150-character overlap and persist stable positions plus normalized search text.

- [ ] **Step 4: Implement lifecycle API**

Add multipart upload, list, detail, archive/activate, and retry endpoints. For the MVP, process with `BackgroundTasks`; commit `PROCESSING` first and update to `READY` or `FAILED` in a new DB session. SHA-256 duplicates return 409 with the existing document id. Only READY+active chunks are returned to retrieval.

- [ ] **Step 5: Verify API and migrations**

Run: `cd apps/api && DATABASE_URL=sqlite:////private/tmp/helpflow-task4.db pytest tests -q --ignore=tests/test_migrations.py && env -u DATABASE_URL pytest tests/test_migrations.py -q`
Expected: all API tests pass.

- [ ] **Step 6: Commit**

```bash
git add apps/api docker-compose.yml .env.example
git commit -m "feat(knowledge): ingest and manage company documents"
```

### Task 5: Evidence validator and hybrid retrieval

**Files:**
- Create: `services/ai/helpflow_ai/evidence.py`
- Create: `services/ai/helpflow_ai/answer_policy.py`
- Create: `services/ai/tests/test_evidence.py`
- Create: `services/ai/tests/test_answer_policy.py`
- Modify: `services/ai/helpflow_ai/schemas.py`
- Modify: `services/ai/helpflow_ai/retrieval.py`
- Modify: `services/ai/helpflow_ai/prompts.py`
- Modify: `services/ai/helpflow_ai/engine.py`

**Interfaces:**
- Consumes: built-in `KnowledgeChunk` plus Task 4 persisted chunks mapped into the same schema.
- Produces: `EvidenceAnswer`, `EvidenceValidator.validate`, `AnswerPolicy.route`, ranked `KnowledgeRetriever.search` with phrase/token/section scoring.

- [ ] **Step 1: Write failing evidence and policy tests**

```python
def test_rejects_quote_not_present_in_claimed_chunk():
    answer = EvidenceAnswer(answer="VPN разрешён всем", claims=[
        EvidenceClaim(text="VPN разрешён всем", source_id="doc:1:0", quote="разрешён всем"),
    ], confidence=0.9)
    with pytest.raises(UnsupportedEvidence):
        EvidenceValidator({"doc:1:0": "VPN доступен только штатным сотрудникам"}).validate(answer)

def test_company_policy_without_source_routes_to_operator():
    route = AnswerPolicy().route("Сколько дней отпуска положено?", matches=[])
    assert route.kind == "operator"
```

- [ ] **Step 2: Run tests and verify RED**

Run: `pytest services/ai/tests/test_evidence.py services/ai/tests/test_answer_policy.py -q`
Expected: FAIL because evidence and answer-policy modules are absent.

- [ ] **Step 3: Implement retrieval and exact evidence validation**

Rank exact phrases, normalized token coverage, title/keyword matches, playbook affinity, and document recency without requiring an embedding download. Validate source membership, Unicode-normalized exact quote containment, claim coverage, answer length, confidence threshold, and forbidden secret patterns.

- [ ] **Step 4: Update prompts and remove exact prepared-message equality**

For grounded routes, request JSON `answer`, `claims[{text,source_id,quote}]`, `confidence`, `needs_operator`, `reason`. Preserve deterministic action and safety notice but replace `_same_prepared_message` with evidence validation. Invalid evidence returns the deterministic safe decision and records a specific fallback reason.

- [ ] **Step 5: Verify AI suite**

Run: `pytest services/ai/tests -q`
Expected: all AI tests pass.

- [ ] **Step 6: Commit**

```bash
git add services/ai
git commit -m "feat(ai): validate cited claims and rank company knowledge"
```

### Task 6: Three-tier answer orchestration and latency controls

**Files:**
- Create: `apps/api/app/services/knowledge_provider.py`
- Create: `apps/api/tests/test_general_answer_routing.py`
- Modify: `apps/api/app/services/triage.py`
- Modify: `apps/api/app/core/config.py`
- Modify: `services/ai/helpflow_ai/engine.py`
- Modify: `services/ai/helpflow_ai/llm.py`
- Modify: `services/ai/helpflow_ai/prompts.py`
- Modify: `services/ai/helpflow_ai/schemas.py`
- Modify: `services/ai/tests/test_llm.py`
- Modify: `services/ai/tests/test_engine.py`
- Modify: `.env.example`
- Modify: `docker-compose.yml`

**Interfaces:**
- Consumes: Task 4 READY chunks and Task 5 policy/evidence validator.
- Produces: one-call-per-turn orchestration, `answer_mode` (`company`, `playbook`, `general`, `operator`), source metadata, bounded Ollama request.

- [ ] **Step 1: Write failing route and call-count tests**

```python
def test_low_risk_unknown_question_gets_labelled_general_guidance(fake_llm):
    decision = engine(fake_llm).answer("Как очистить кэш браузера?", corporate_chunks=[])
    assert decision.answer_mode == "general"
    assert "Общая рекомендация" in decision.message
    assert fake_llm.calls == 1

def test_company_policy_without_source_escalates_without_llm(fake_llm):
    decision = engine(fake_llm).answer("Какой у нас лимит командировочных?", corporate_chunks=[])
    assert decision.action == DecisionAction.ESCALATE
    assert fake_llm.calls == 0
```

- [ ] **Step 2: Run tests and verify RED**

Run: `pytest services/ai/tests/test_engine.py services/ai/tests/test_llm.py -q && cd apps/api && pytest tests/test_general_answer_routing.py -q`
Expected: FAIL because answer modes and general routing do not exist.

- [ ] **Step 3: Implement one-call orchestration**

Fast smalltalk, security, critical incident, and playbook steps stay deterministic. Company matches use evidence mode. Low-risk unknown technical questions use a separate constrained general prompt and label. Company/HR/finance/legal/security/access questions without evidence skip the model and escalate. A failed general step or explicit user request escalates with the attempted advice included in the card.

- [ ] **Step 4: Bound Ollama latency**

Set the Ollama default timeout to 20 seconds, `num_predict` to 320, `num_ctx` to 4096, `temperature` to 0.1, `keep_alive` to `15m`, and no retries. Add a non-blocking best-effort warmup during API lifespan. Ensure each turn stores latency, answer mode, source ids, and fallback reason.

- [ ] **Step 5: Verify AI and API suites**

Run: `pytest services/ai/tests -q && cd apps/api && DATABASE_URL=sqlite:////private/tmp/helpflow-task6.db pytest tests -q --ignore=tests/test_migrations.py`
Expected: all selected tests pass.

- [ ] **Step 6: Commit**

```bash
git add services/ai apps/api .env.example docker-compose.yml
git commit -m "feat(ai): add fast three-tier answer orchestration"
```

### Task 7: Knowledge UI, answer provenance and end-to-end verification

**Files:**
- Create: `apps/web/src/features/knowledge/KnowledgePage.tsx`
- Create: `apps/web/src/features/knowledge/KnowledgePage.css`
- Create: `apps/web/src/features/knowledge/KnowledgePage.test.tsx`
- Create: `apps/web/src/components/AnswerSources.tsx`
- Create: `apps/api/tests/test_managed_rag_acceptance.py`
- Modify: `apps/web/src/App.tsx`
- Modify: `apps/web/src/components/Header.tsx`
- Modify: `apps/web/src/api/client.ts`
- Modify: `apps/web/src/api/types.ts`
- Modify: `apps/web/src/features/conversation/MessageThread.tsx`
- Modify: `apps/web/src/features/conversation/useConversation.ts`
- Modify: `apps/web/src/test/server.ts`
- Modify: `README.md`
- Modify: `apps/api/app/seed_demo.py`

**Interfaces:**
- Consumes: document admin API, answer mode/source metadata, all previous tasks.
- Produces: `/admin/knowledge`, visible source citations/general label, complete demo and operator fallback flow.

- [ ] **Step 1: Write failing frontend and acceptance tests**

```tsx
it("uploads a company document and renders READY status", async () => {
  renderKnowledgePage();
  const file = new File(["VPN работает через корпоративный шлюз"], "vpn.txt", { type: "text/plain" });
  await user.upload(screen.getByLabelText("Документ"), file);
  await user.click(screen.getByRole("button", { name: "Загрузить" }));
  expect(await screen.findByText("Готов")).toBeInTheDocument();
});
```

```python
def test_uploaded_rule_is_cited_and_unknown_policy_escalates(admin_client, employee_client):
    upload_ready_text(admin_client, "vpn.txt", "VPN разрешён только штатным сотрудникам.")
    grounded = ask(employee_client, "Кому разрешён VPN?")
    assert grounded["answer_mode"] == "company"
    assert grounded["answer_sources"][0]["document_name"] == "vpn.txt"
    unknown = ask(employee_client, "Какой у нас лимит командировочных?")
    assert unknown["status"] == "ESCALATED"
```

- [ ] **Step 2: Run tests and verify RED**

Run: `cd apps/web && npm test -- --run src/features/knowledge/KnowledgePage.test.tsx && cd ../../apps/api && pytest tests/test_managed_rag_acceptance.py -q`
Expected: FAIL because the knowledge UI and response provenance are missing.

- [ ] **Step 3: Implement knowledge UI and chat provenance**

Add admin navigation, drag-and-drop/file picker, category/version fields, status polling, failure details, archive/reactivate/retry actions, and extracted-text preview. In the chat, render corporate source names and quotes under verified answers, a visible general-guidance badge for general mode, and a handoff reason for operator mode.

- [ ] **Step 4: Update demo data and documentation**

Seed one READY policy document, one managed specialist, personal metrics history, and deterministic examples for company-grounded, general, and operator routes. Document Docker setup, accepted formats, storage volume, account reset behavior, Ollama warmup, and exact demo steps for macOS and Windows.

- [ ] **Step 5: Run full verification**

Run: `pytest services/ai/tests -q`
Expected: all AI tests pass.

Run: `cd apps/api && DATABASE_URL=sqlite:////private/tmp/helpflow-final.db pytest tests -q --ignore=tests/test_migrations.py && env -u DATABASE_URL pytest tests/test_migrations.py -q`
Expected: all API tests pass; PostgreSQL smoke may skip only when the integration service is absent.

Run: `cd apps/web && npm test -- --run && npm run lint && npm run build`
Expected: tests, lint, and production build exit 0.

- [ ] **Step 6: Commit**

```bash
git add apps/web apps/api README.md
git commit -m "feat(web): manage knowledge and show verified answer sources"
```

### Task 8: Whole-branch review and handoff

**Files:**
- Modify only files required by verified review findings.

**Interfaces:**
- Consumes: completed branch, spec, plan, ledger, full test evidence.
- Produces: review-clean branch and user-facing run instructions.

- [ ] **Step 1: Generate the review package**

Run: `review-package docs/superpowers/plans/2026-09-28-admin-rag-profiles.md $(git merge-base origin/main HEAD) HEAD`
Expected: package contains all commits, test evidence, rulings, and diff summary.

- [ ] **Step 2: Run a fresh whole-branch review**

Review against the spec and Review Focus, grading findings by user impact. For each Critical/Important finding, first add a regression test that fails, then implement the fix and run the full affected suite. Record Minor findings in the ledger.

- [ ] **Step 3: Verify the final tree**

Run the AI, API, migration, frontend test, lint, and build commands from Task 7.
Expected: every available suite passes; any external-service skip is named explicitly.

- [ ] **Step 4: Commit review fixes**

```bash
git add -A
git commit -m "fix: close managed rag review findings"
```

Do not create an empty commit when review finds nothing.
