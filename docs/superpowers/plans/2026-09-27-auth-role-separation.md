# HelpFlow Authentication and Role Separation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить безопасную регистрацию и вход с реальными письмами через Яндекс SMTP, разделить кабинеты сотрудника и специалиста и изолировать данные по ролям.

**Architecture:** FastAPI хранит пользователей, Argon2id-хеши, одноразовые email-токены и серверные сессии; браузер получает только случайную `HttpOnly` cookie. React загружает `/api/auth/me`, применяет role guards и показывает отдельные auth-, employee- и operator-layout без переключателя ролей.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Pydantic 2, `argon2-cffi`, стандартный `smtplib`, React 19, React Router 7, TypeScript 6, Vitest, Testing Library, pytest.

**Spec:** `docs/superpowers/specs/2026-09-27-auth-role-separation-design.md`

## Global Constraints

- Самостоятельная регистрация создаёт только роль `employee`; `operator` создаётся только по одноразовому приглашению.
- Email обязателен к подтверждению до доступа к кабинетам.
- Пароль содержит 10–128 символов, строчную и заглавную букву и цифру, без пробельных символов.
- Сырые пароли, session token, email token, invite token и SMTP-пароль не сохраняются и не логируются.
- Cookie: `HttpOnly`, `SameSite=Lax`, `Path=/`; `Secure=true` вне локальной разработки.
- Обычная сессия живёт 12 часов, с «Запомнить меня» — 30 дней.
- SMTP по умолчанию: `smtp.yandex.ru:465`, SSL; секреты только в `.env`.
- Новые обращения всегда имеют `owner_id`; старые обращения без владельца доступны только специалистам.
- Существующие несвязанные изменения рабочего дерева сохраняются и не входят в тематические коммиты.

## Review Focus

- Unicode-имена (`Анна-Мария`, `О'Коннор`) принимаются, а цифры и управляющие символы отклоняются — Task 3.
- Повторное использование и гонка двух запросов с одним email-токеном дают ровно один успех — Task 4.
- Cookie, истёкшая или отозванная между `/me` и изменяющим запросом, возвращает `401`, не выполняя изменение — Task 5.
- Сотрудник, угадавший UUID чужого обращения, получает `404`, не раскрывающий существование записи — Task 6.
- Ошибка SMTP после создания аккаунта не удаляет пользователя и приводит к экрану повторной отправки — Tasks 4 и 8.

---

### Task 1: Security configuration and password primitives

**Files:**
- Modify: `apps/api/requirements.txt`
- Modify: `apps/api/app/core/config.py`
- Create: `apps/api/app/core/security.py`
- Create: `apps/api/tests/test_security.py`
- Modify: `.env.example`

**Interfaces:**
- Produces: `hash_password(password: str) -> str`, `verify_password(hash: str, password: str) -> bool`, `new_token() -> str`, `hash_token(token: str) -> str`, `utc_now() -> datetime`.
- Produces settings for cookie lifetime, trusted frontend URL and SMTP without exposing their values to clients.

- [ ] **Step 1: Add failing tests for password and token primitives**

```python
from app.core.security import hash_password, hash_token, new_token, verify_password


def test_password_hash_is_argon2_and_verifies_only_original():
    encoded = hash_password("StrongPassword7")
    assert encoded.startswith("$argon2id$")
    assert verify_password(encoded, "StrongPassword7") is True
    assert verify_password(encoded, "WrongPassword7") is False


def test_tokens_are_random_and_only_hash_is_stable():
    first, second = new_token(), new_token()
    assert first != second
    assert len(first) >= 43
    assert hash_token(first) == hash_token(first)
    assert hash_token(first) != hash_token(second)
```

- [ ] **Step 2: Verify the tests fail before dependencies and module exist**

Run: `cd apps/api && ../../.venv/bin/pytest tests/test_security.py -v`  
Expected: FAIL importing `app.core.security`.

- [ ] **Step 3: Add `argon2-cffi==25.1.0` and implement primitives**

```python
# apps/api/app/core/security.py
from datetime import UTC, datetime
from hashlib import sha256
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)

def utc_now() -> datetime:
    return datetime.now(UTC)

def hash_password(password: str) -> str:
    return _hasher.hash(password)

def verify_password(encoded: str, password: str) -> bool:
    try:
        return _hasher.verify(encoded, password)
    except (VerifyMismatchError, InvalidHashError):
        return False

def new_token() -> str:
    return secrets.token_urlsafe(32)

def hash_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()
```

Extend `Settings` with `app_public_url`, `session_cookie_name`, session TTLs, `cookie_secure`, SMTP fields and validation that production-like mode rejects blank SMTP credentials. Add the same names with empty safe values to `.env.example`; never add a real address or password.

- [ ] **Step 4: Run focused tests**

Run: `cd apps/api && ../../.venv/bin/pytest tests/test_security.py tests/test_config.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/requirements.txt apps/api/app/core/config.py apps/api/app/core/security.py apps/api/tests/test_security.py apps/api/tests/test_config.py .env.example
git commit -m "feat(auth): add security configuration and password hashing"
```

### Task 2: Authentication persistence and migration

**Files:**
- Create: `apps/api/app/models/auth.py`
- Modify: `apps/api/app/models/__init__.py`
- Modify: `apps/api/app/models/conversation.py`
- Create: `apps/api/alembic/versions/20260927_0004_auth_and_ownership.py`
- Modify: `apps/api/tests/test_database.py`
- Modify: `apps/api/tests/test_migrations.py`

**Interfaces:**
- Produces SQLAlchemy models `User`, `AuthSession`, `EmailToken`, `OperatorInvite` and enums represented as constrained strings.
- Adds `Conversation.owner_id: str | None` and `Conversation.owner`.

- [ ] **Step 1: Write failing model tests**

```python
def test_user_session_and_owned_conversation_persist(db_session):
    user = User(first_name="Анна", last_name="Иванова", email="anna@example.ru",
                department="it", password_hash="hash", role="employee")
    db_session.add(user)
    db_session.flush()
    conversation = Conversation(owner_id=user.id)
    session = AuthSession(user_id=user.id, token_hash="a" * 64,
                          expires_at=utc_now() + timedelta(hours=12))
    db_session.add_all([conversation, session])
    db_session.commit()
    assert conversation.owner.email == "anna@example.ru"
    assert session.user.role == "employee"
```

Add migration assertions for the four tables, indexes, foreign keys and nullable `conversations.owner_id`, while preserving an existing unowned conversation.

- [ ] **Step 2: Run tests and observe missing models/schema**

Run: `cd apps/api && ../../.venv/bin/pytest tests/test_database.py tests/test_migrations.py -v`  
Expected: FAIL because auth models and migration are absent.

- [ ] **Step 3: Implement focused models and Alembic upgrade/downgrade**

`users.email` uses a unique index over `lower(email)` in PostgreSQL and stores normalized lowercase input. Each token table has an index on `token_hash`; sessions additionally index `user_id` and `expires_at`. Add `ondelete="CASCADE"` from auth child records to users and `ondelete="SET NULL"` from conversations to users.

- [ ] **Step 4: Verify SQLite models and migration round trip**

Run: `cd apps/api && ../../.venv/bin/pytest tests/test_database.py tests/test_migrations.py -v`  
Expected: PASS, including upgrade → downgrade → upgrade.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/models apps/api/alembic/versions/20260927_0004_auth_and_ownership.py apps/api/tests/test_database.py apps/api/tests/test_migrations.py
git commit -m "feat(auth): add user session and token persistence"
```

### Task 3: Auth schemas and repository

**Files:**
- Create: `apps/api/app/schemas/auth.py`
- Create: `apps/api/app/repositories/auth.py`
- Create: `apps/api/tests/test_auth_schemas.py`
- Create: `apps/api/tests/test_auth_repository.py`

**Interfaces:**
- Produces request models `EmployeeRegister`, `OperatorRegister`, `LoginRequest`, `TokenRequest`, `ForgotPasswordRequest`, `ResetPasswordRequest`.
- Produces response model `CurrentUser` and error shape `ApiErrorBody`.
- Produces `AuthRepository` methods `get_user_by_email`, `get_user`, `add_user`, `add_session`, `get_session_by_token_hash`, `revoke_session`, `revoke_all_sessions`, `add_email_token`, `consume_email_token`, `consume_invite`.

- [ ] **Step 1: Write failing schema tests for valid Unicode and invalid boundaries**

```python
@pytest.mark.parametrize("name", ["Анна-Мария", "O'Connor", "Ли"])
def test_registration_accepts_supported_names(name):
    payload = EmployeeRegister(first_name=name, last_name="Иванов", email=" A@EXAMPLE.RU ",
        department="it", password="StrongPass7", password_confirmation="StrongPass7",
        accepted_terms=True)
    assert payload.email == "a@example.ru"

@pytest.mark.parametrize("password", ["short7A", "alllowercase7", "ALLUPPERCASE7", "NoDigitsHere", "Has Space7A"])
def test_registration_rejects_weak_password(password):
    with pytest.raises(ValidationError):
        valid_employee(password=password, password_confirmation=password)
```

Add cases for names with digits/control characters, unknown department, mismatch, false terms, overlong email and normalized duplicate lookup.

- [ ] **Step 2: Run focused tests and verify failure**

Run: `cd apps/api && ../../.venv/bin/pytest tests/test_auth_schemas.py tests/test_auth_repository.py -v`  
Expected: FAIL importing new modules.

- [ ] **Step 3: Implement schemas and transaction-safe repository**

Use Pydantic validators to normalize names and email. `consume_email_token` and `consume_invite` must issue an atomic conditional `UPDATE ... WHERE used_at IS NULL AND expires_at > now`, returning success only when one row changes.

- [ ] **Step 4: Run schema and repository tests**

Run: `cd apps/api && ../../.venv/bin/pytest tests/test_auth_schemas.py tests/test_auth_repository.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/schemas/auth.py apps/api/app/repositories/auth.py apps/api/tests/test_auth_schemas.py apps/api/tests/test_auth_repository.py
git commit -m "feat(auth): validate identities and persist auth state"
```

### Task 4: Email delivery, verification and reset services

**Files:**
- Create: `apps/api/app/services/email.py`
- Create: `apps/api/app/services/auth.py`
- Create: `apps/api/app/templates/email/verify.html`
- Create: `apps/api/app/templates/email/verify.txt`
- Create: `apps/api/app/templates/email/reset.html`
- Create: `apps/api/app/templates/email/reset.txt`
- Create: `apps/api/tests/test_email.py`
- Create: `apps/api/tests/test_auth_service.py`

**Interfaces:**
- Produces `EmailSender.send(message: EmailMessage) -> None`, `SmtpEmailSender`, `MemoryEmailSender`.
- Produces `AuthService.register_employee`, `register_operator`, `verify_email`, `resend_verification`, `request_password_reset`, `reset_password`, `login`, `logout`.
- Defines domain errors `DuplicateEmail`, `InvalidCredentials`, `EmailNotVerified`, `InvalidOrExpiredToken`, `InvalidInvite`, `EmailDeliveryFailed`.

- [ ] **Step 1: Write failing service tests using `MemoryEmailSender`**

```python
def test_registration_survives_delivery_failure(db_session):
    sender = FailingEmailSender()
    service = make_auth_service(db_session, sender)
    with pytest.raises(EmailDeliveryFailed):
        service.register_employee(valid_employee())
    db_session.expire_all()
    assert AuthRepository(db_session).get_user_by_email("a@example.ru") is not None

def test_verification_token_is_single_use_even_for_two_calls(service, outbox):
    service.register_employee(valid_employee())
    token = outbox.last_token
    service.verify_email(token)
    with pytest.raises(InvalidOrExpiredToken):
        service.verify_email(token)
```

Add reset expiry, reset revokes every session, previous active verification token invalidation, operator invite email match and HTML escaping tests.

- [ ] **Step 2: Run tests and verify missing service failure**

Run: `cd apps/api && ../../.venv/bin/pytest tests/test_email.py tests/test_auth_service.py -v`  
Expected: FAIL importing email/auth services.

- [ ] **Step 3: Implement SMTP adapter and transactional auth service**

Build `EmailMessage` with both `text/plain` and `text/html`; send using `smtplib.SMTP_SSL(host, port, timeout=10)`, authenticate with app password and set the configured From header. Commit the user/token before attempting SMTP so delivery failure is recoverable. URLs use only `settings.app_public_url` plus URL-encoded token.

- [ ] **Step 4: Verify service behavior without external network**

Run: `cd apps/api && ../../.venv/bin/pytest tests/test_email.py tests/test_auth_service.py -v`  
Expected: PASS; tests patch `SMTP_SSL` or use `MemoryEmailSender` and never contact Яндекс.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/services/email.py apps/api/app/services/auth.py apps/api/app/templates/email apps/api/tests/test_email.py apps/api/tests/test_auth_service.py
git commit -m "feat(auth): send verification and password reset emails"
```

### Task 5: Auth API, cookies, origin checks and throttling

**Files:**
- Create: `apps/api/app/api/dependencies/auth.py`
- Create: `apps/api/app/api/routes/auth.py`
- Create: `apps/api/app/services/rate_limit.py`
- Modify: `apps/api/app/main.py`
- Modify: `apps/api/tests/conftest.py`
- Create: `apps/api/tests/test_auth_api.py`

**Interfaces:**
- Produces dependencies `get_current_user`, `require_verified_user`, `require_employee`, `require_operator`.
- Produces `/api/auth/*` endpoints defined by the spec.
- Produces `InMemoryRateLimiter.check(bucket: str, key: str, limit: int, window: timedelta) -> None` raising `RateLimitExceeded`.

- [ ] **Step 1: Write failing API tests**

```python
def test_login_sets_hardened_cookie(client, verified_employee):
    response = client.post("/api/auth/login", json={"email": verified_employee.email,
        "password": "StrongPass7", "remember_me": False})
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Path=/" in cookie
    assert response.json()["role"] == "employee"

def test_revoked_cookie_cannot_mutate_state(client, logged_in_employee):
    client.post("/api/auth/logout")
    response = client.post("/api/conversations")
    assert response.status_code == 401

def test_forgot_password_is_neutral_for_unknown_email(client):
    assert client.post("/api/auth/forgot-password", json={"email": "missing@example.ru"}).status_code == 202
```

Add invalid Origin, unverified user, expiry, `429`, email-delivery `503` with recoverable code, and cookie removal tests.

- [ ] **Step 2: Run endpoint tests and verify 404/import failures**

Run: `cd apps/api && ../../.venv/bin/pytest tests/test_auth_api.py -v`  
Expected: FAIL because router/dependencies are absent.

- [ ] **Step 3: Implement router, dependency chain and rate limiter**

Map domain errors to stable codes such as `duplicate_email`, `email_not_verified`, `invalid_credentials`, `invalid_or_expired_token`, `email_delivery_failed`, and return field maps for validation. Read the cookie, hash it, load a non-revoked non-expired session and update `last_seen_at` at most once per five minutes.

- [ ] **Step 4: Run auth API tests**

Run: `cd apps/api && ../../.venv/bin/pytest tests/test_auth_api.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/api/dependencies/auth.py apps/api/app/api/routes/auth.py apps/api/app/services/rate_limit.py apps/api/app/main.py apps/api/tests/conftest.py apps/api/tests/test_auth_api.py
git commit -m "feat(auth): expose secure session API"
```

### Task 6: Protect conversations and operator queue

**Files:**
- Modify: `apps/api/app/api/routes/conversations.py`
- Modify: `apps/api/app/api/routes/operator.py`
- Modify: `apps/api/app/repositories/conversations.py`
- Modify: `apps/api/app/services/dialogue.py`
- Modify: `apps/api/app/services/triage.py`
- Modify: `apps/api/tests/test_conversations.py`
- Modify: `apps/api/tests/test_operator.py`
- Create: `apps/api/tests/test_authorization.py`

**Interfaces:**
- Changes `ConversationRepository.get(id, owner_id: str | None = None)` so employee lookups include owner filtering.
- Changes conversation creation to `create_conversation(owner_id: str)`.
- Adds `GET /api/conversations` for the current employee's history.
- Operator routes consume `require_operator`; conversation routes consume `require_employee`.

- [ ] **Step 1: Write failing authorization tests**

```python
def test_employee_cannot_discover_another_users_conversation(client, employee_a, employee_b):
    conversation = create_owned_conversation(employee_b.id)
    login_as(client, employee_a)
    assert client.get(f"/api/conversations/{conversation.id}").status_code == 404
    assert client.post(f"/api/conversations/{conversation.id}/messages",
        json={"content": "test"}).status_code == 404

def test_employee_cannot_list_operator_queue(client, logged_in_employee):
    assert client.get("/api/operator/tickets").status_code == 403

def test_operator_sees_legacy_unowned_escalations(client, logged_in_operator, legacy_escalation):
    assert legacy_escalation.id in {item["id"] for item in client.get("/api/operator/tickets").json()}
```

- [ ] **Step 2: Run focused tests and observe unauthorized access**

Run: `cd apps/api && ../../.venv/bin/pytest tests/test_authorization.py -v`  
Expected: FAIL because current endpoints are public.

- [ ] **Step 3: Thread authenticated identity through routes, repository and services**

Never accept `owner_id` from the payload. Filter by owner in the same SQL query rather than loading then comparing. Return `404` for non-owned UUIDs. Update test fixtures to override `get_current_user` explicitly instead of disabling checks inside production code.

- [ ] **Step 4: Run all API tests**

Run: `cd apps/api && ../../.venv/bin/pytest -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/api/routes apps/api/app/repositories/conversations.py apps/api/app/services apps/api/tests
git commit -m "feat(auth): isolate employee cases and protect operator queue"
```

### Task 7: Frontend auth API and session state

**Files:**
- Modify: `apps/web/src/api/client.ts`
- Modify: `apps/web/src/api/types.ts`
- Modify: `apps/web/src/api/errors.ts`
- Create: `apps/web/src/features/auth/AuthProvider.tsx`
- Create: `apps/web/src/features/auth/guards.tsx`
- Create: `apps/web/src/features/auth/validation.ts`
- Create: `apps/web/src/features/auth/AuthProvider.test.tsx`
- Create: `apps/web/src/features/auth/validation.test.ts`
- Modify: `apps/web/src/main.tsx`

**Interfaces:**
- Produces `AuthUser`, registration/login/reset payload types.
- Produces `useAuth(): { user, status, login, logout, refresh }`.
- Produces `<GuestOnly>`, `<RequireEmployee>`, `<RequireOperator>`.
- Changes every request to use `credentials: "include"`.

- [ ] **Step 1: Write failing session and validation tests**

```tsx
it("redirects an employee away from the operator area", async () => {
  server.use(http.get("*/api/auth/me", () => HttpResponse.json(employeeUser)));
  renderAt(<RequireOperator><div>queue</div></RequireOperator>, "/operator");
  expect(await screen.findByText(/перенаправление/i)).toBeInTheDocument();
  await waitFor(() => expect(location.pathname).toBe("/employee"));
});
```

Validation tests mirror server rules, including Unicode names, password boundaries and accepted terms.

- [ ] **Step 2: Run tests and verify missing modules**

Run: `cd apps/web && npm test -- --run src/features/auth/AuthProvider.test.tsx src/features/auth/validation.test.ts`  
Expected: FAIL importing auth modules.

- [ ] **Step 3: Implement typed endpoints, provider, guards and validation**

On initial load call `/api/auth/me`; treat `401` as anonymous and surface network failures without pretending the user is logged out. `logout()` waits for server success, clears local auth state and navigates to `/login`.

- [ ] **Step 4: Run focused frontend tests**

Run: `cd apps/web && npm test -- --run src/features/auth/AuthProvider.test.tsx src/features/auth/validation.test.ts`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/api apps/web/src/features/auth apps/web/src/main.tsx
git commit -m "feat(web): add authenticated session state and role guards"
```

### Task 8: Auth screens and recoverable email delivery states

**Files:**
- Create: `apps/web/src/features/auth/AuthLayout.tsx`
- Create: `apps/web/src/features/auth/AuthLayout.css`
- Create: `apps/web/src/features/auth/Field.tsx`
- Create: `apps/web/src/features/auth/LoginPage.tsx`
- Create: `apps/web/src/features/auth/RegisterPage.tsx`
- Create: `apps/web/src/features/auth/VerifyEmailPage.tsx`
- Create: `apps/web/src/features/auth/ForgotPasswordPage.tsx`
- Create: `apps/web/src/features/auth/ResetPasswordPage.tsx`
- Create: `apps/web/src/features/auth/OperatorRegisterPage.tsx`
- Create: `apps/web/src/features/auth/AuthPages.test.tsx`

**Interfaces:**
- Consumes auth API/types/validation from Task 7.
- Produces complete public registration, login, verification and reset UI.

- [ ] **Step 1: Write failing interaction tests**

```tsx
it("keeps the registration result when email delivery failed", async () => {
  server.use(http.post("*/api/auth/register", () => HttpResponse.json(
    { code: "email_delivery_failed", message: "Аккаунт создан" }, { status: 503 })));
  renderAt(<RegisterPage />, "/register");
  await fillValidRegistration();
  await userEvent.click(screen.getByRole("button", { name: "Создать аккаунт" }));
  expect(await screen.findByText(/аккаунт создан/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /отправить письмо повторно/i })).toBeEnabled();
});
```

Add inline field errors, duplicate email, pending buttons, neutral forgot response, invalid/expired link, resend cooldown and invite-required tests.

- [ ] **Step 2: Run screen tests and verify missing components**

Run: `cd apps/web && npm test -- --run src/features/auth/AuthPages.test.tsx`  
Expected: FAIL importing pages.

- [ ] **Step 3: Implement responsive accessible auth UI**

Use semantic `<label>`, `aria-describedby`, `aria-invalid`, alert regions and password visibility toggles. Do not log form values. Preserve non-secret fields after server failure; always clear password fields after an authentication failure.

- [ ] **Step 4: Run auth page tests**

Run: `cd apps/web && npm test -- --run src/features/auth/AuthPages.test.tsx`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/features/auth
git commit -m "feat(web): add registration login and recovery screens"
```

### Task 9: Separate employee and operator application shells

**Files:**
- Modify: `apps/web/src/App.tsx`
- Modify: `apps/web/src/components/Header.tsx`
- Modify: `apps/web/src/components/Header.css`
- Create: `apps/web/src/components/AppShell.tsx`
- Create: `apps/web/src/pages/EmployeePage.tsx`
- Create: `apps/web/src/pages/EmployeeHistoryPage.tsx`
- Modify: `apps/web/src/pages/OperatorPageRoute.tsx`
- Modify: `apps/web/src/features/conversation/useConversation.ts`
- Create: `apps/web/src/pages/Routes.test.tsx`

**Interfaces:**
- Consumes guards and user state from Task 7.
- Produces route tree with public auth routes, `/employee`, `/employee/history` and `/operator`.
- Header accepts only role-specific nav supplied by `AppShell`; no cross-role links remain.

- [ ] **Step 1: Write failing route-separation tests**

```tsx
it("shows no specialist switch in the employee cabinet", async () => {
  mockCurrentUser(employeeUser);
  renderApplicationAt("/employee");
  expect(await screen.findByText("Мои обращения")).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Специалист" })).not.toBeInTheDocument();
});

it("redirects root according to role", async () => {
  mockCurrentUser(operatorUser);
  renderApplicationAt("/");
  await waitFor(() => expect(location.pathname).toBe("/operator"));
});
```

Add guest redirect, operator shell, logout, history loading and no foreign navigation tests.

- [ ] **Step 2: Run route tests and verify current shared header fails them**

Run: `cd apps/web && npm test -- --run src/pages/Routes.test.tsx`  
Expected: FAIL because `/` and `/operator` share the current switcher.

- [ ] **Step 3: Implement separate shells and employee history**

Move the existing conversation page under `/employee`. Replace localStorage-only conversation discovery with the authenticated `GET /api/conversations` history while retaining the active conversation ID only as a UI convenience. Operator shell exposes queue-specific navigation only.

- [ ] **Step 4: Run all frontend tests, lint and build**

Run: `cd apps/web && npm test -- --run && npm run lint && npm run build`  
Expected: PASS and successful Vite production build.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src
git commit -m "feat(web): separate employee and operator cabinets"
```

### Task 10: Integration verification and setup documentation

**Files:**
- Modify: `README.md`
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Create: `apps/api/tests/test_auth_acceptance.py`
- Modify: `apps/web/src/test/server.ts`

**Interfaces:**
- Documents exact Яндекс app-password setup without including credentials.
- Provides a deterministic acceptance test spanning registration → verification → login → owned conversation → logout → operator denial.

- [ ] **Step 1: Add the failing backend acceptance flow**

```python
def test_employee_authentication_acceptance_flow(client, outbox):
    assert client.post("/api/auth/register", json=valid_registration_json()).status_code == 201
    token = outbox.last_token
    assert client.post("/api/auth/verify-email", json={"token": token}).status_code == 204
    assert client.post("/api/auth/login", json={"email": "a@example.ru",
        "password": "StrongPass7", "remember_me": False}).status_code == 200
    created = client.post("/api/conversations")
    assert created.status_code == 201
    assert client.get("/api/operator/tickets").status_code == 403
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get(f"/api/conversations/{created.json()['id']}").status_code == 401
```

- [ ] **Step 2: Run acceptance test and fix only integration defects it reveals**

Run: `cd apps/api && ../../.venv/bin/pytest tests/test_auth_acceptance.py -v`  
Expected: PASS after wiring corrections; do not weaken guards or assertions.

- [ ] **Step 3: Document safe local setup**

README instructions must say: enable two-factor authentication in Yandex ID, create an application password for mail, copy `.env.example` to `.env`, set `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`, and keep `.env` untracked. Add Compose passthrough for auth/SMTP variables without defaults containing secrets.

- [ ] **Step 4: Run full verification from repository root**

```bash
cd apps/api && ../../.venv/bin/pytest -v
cd ../web && npm test -- --run && npm run lint && npm run build
```

Expected: all backend tests pass, all frontend tests pass, lint exits 0 and production build succeeds.

- [ ] **Step 5: Inspect secret leakage and migration state**

Run: `git diff --check && git grep -nE '(SMTP_PASSWORD=.+|ya29\.|password.{0,5}=.{8,})' -- ':!package-lock.json' ':!uv.lock'`  
Expected: no whitespace errors and no real credentials. Review `git status --short` so only intentional files enter the commit.

- [ ] **Step 6: Commit**

```bash
git add README.md docker-compose.yml .env.example apps/api/tests/test_auth_acceptance.py apps/web/src/test/server.ts
git commit -m "docs(auth): add Yandex SMTP setup and acceptance coverage"
```

### Task 11: Manual browser smoke test

**Files:**
- No production files expected; fix only defects proven by the smoke test and add a regression test beside the owning component.

**Interfaces:**
- Consumes the complete application from Tasks 1–10.
- Produces visual and behavioral evidence that role separation works at desktop and mobile widths.

- [ ] **Step 1: Start API and web app with a test mailbox configuration**

Run API and Vite using the documented commands. Use a dedicated test recipient; do not expose SMTP credentials in terminal output or screenshots.

- [ ] **Step 2: Complete the employee flow**

Register, receive a real Yandex-delivered verification email, verify, log in, create an appeal, open history and log out. Confirm the employee UI contains no operator navigation.

- [ ] **Step 3: Complete the operator isolation flow**

Use a seeded one-time invite, register an operator, verify email, log in and open the queue. Confirm direct navigation to `/employee` redirects back to `/operator`.

- [ ] **Step 4: Check responsive and keyboard behavior**

At desktop and 390 px viewport widths, tab through each form, trigger field errors, verify focus placement and confirm no horizontal overflow.

- [ ] **Step 5: Re-run automated verification after any smoke-test fix**

Run: `cd apps/api && ../../.venv/bin/pytest -v && cd ../web && npm test -- --run && npm run lint && npm run build`  
Expected: all commands exit 0.
