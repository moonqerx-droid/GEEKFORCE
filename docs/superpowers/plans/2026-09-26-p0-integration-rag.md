# P0 Integration and Grounded RAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Объединить рабочие ветки, устранить потерю первого сообщения и добавить контролируемые ответы локальной `qwen3.5:9b`, основанные только на разрешённой базе знаний, с безопасным fallback и сохранением источников.

**Architecture:** Backend state machine продолжает полностью управлять статусами, вопросами, шагами и эскалацией. Новый лексический retriever выбирает фрагменты из существующих playbook и утверждённого FAQ, после чего Qwen может только переформулировать уже выбранное действие в строгий JSON; валидатор проверяет источники, уверенность, безопасность и согласованность с решением. Frontend использует единый метод `startWithMessage`, чтобы первая пользовательская фраза отправлялась по ID и revision непосредственного ответа API.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, SQLAlchemy 2, PostgreSQL 16, Alembic, httpx, PyYAML, pytest, React 19, TypeScript 6, Vite 8, Vitest, Testing Library, MSW, Docker Compose, Ollama `qwen3.5:9b`.

**Spec:** `docs/superpowers/specs/2026-09-26-helpflow-hardening-rag-design.md`

## Global Constraints

- Backend state machine является единственным источником состояния диалога.
- Qwen не меняет статус, срочность, следующий обязательный шаг или решение об эскалации.
- Пользовательские технические ответы используют только фрагменты из `knowledge-base`.
- При невалидном JSON, неизвестном источнике, низкой уверенности, timeout или недоступной Ollama используется rule fallback.
- Для неизвестной проблемы после уточнений и отсутствия уверенного сценария выполняется эскалация в Service Desk L1.
- Первая версия не добавляет embedding-модель, `pgvector`, WebSocket или автономного агента.
- Проект обязан запускаться на macOS и Windows через Docker Compose; секреты не коммитятся.

## Review Focus

- Первое сообщение отправляется ровно один раз даже при медленном `POST /api/conversations`; проверяет Task 2.
- Ответ модели со ссылкой на фрагмент, которого не было в prompt, отбрасывается; проверяет Task 4.
- Timeout или невалидный JSON Ollama не откатывает пользовательский turn и не ломает state machine; проверяет Task 4 и Task 7.
- Приветствие и благодарность не запускают retrieval и не расходуют технический вопрос; проверяет Task 4 и существующие backend regression-тесты.
- Неизвестная проблема после трёх уникальных уточнений не получает выдуманную инструкцию и передаётся L1; проверяет Task 6 и Task 7.

---

### Task 1: Интеграционная база и единый baseline

**Files:**
- Modify by merge: `apps/api/**`, `services/ai/**`, `knowledge-base/**`, `apps/web/**`, `.github/workflows/**`, `docker-compose.yml`, `README.md`
- Create: `.github/workflows/web.yml`

**Interfaces:**
- Consumes: `origin/feat/backend-workflow` at `a468b48`, `origin/frontend` at `b7ad341`.
- Produces: одна интеграционная ветка, в которой существуют backend, AI и frontend и воспроизводятся их исходные тестовые наборы.

- [ ] **Step 1: Merge backend branch without squashing its history**

```bash
git merge --no-ff origin/feat/backend-workflow -m "merge: integrate backend workflow"
```

- [ ] **Step 2: Merge frontend branch without squashing its history**

```bash
git merge --no-ff origin/frontend -m "merge: integrate web frontend"
```

- [ ] **Step 3: Verify the merged file layout**

Run:

```bash
test -f apps/api/app/main.py
test -f services/ai/helpflow_ai/engine.py
test -f apps/web/src/App.tsx
test -f docker-compose.yml
```

Expected: all commands exit with status 0.

- [ ] **Step 4: Add a frontend CI workflow**

Create `.github/workflows/web.yml`:

```yaml
name: Web

on:
  push:
    paths: ["apps/web/**", ".github/workflows/web.yml"]
  pull_request:
    paths: ["apps/web/**", ".github/workflows/web.yml"]

jobs:
  test:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: apps/web
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: npm
          cache-dependency-path: apps/web/package-lock.json
      - run: npm ci
      - run: npm test -- --run
      - run: npm run lint
      - run: npm run build
```

- [ ] **Step 5: Run the untouched baseline**

Run:

```bash
cd apps/api && ../../.venv/bin/pytest -q
cd ../.. && PYTHONPATH=services/ai .venv/bin/pytest services/ai/tests -q
cd apps/web && npm ci && npx vitest run && npm run lint && npm run build
```

Expected: backend and AI pass; web has 18 passing tests, lint has no errors, build succeeds.

- [ ] **Step 6: Commit the CI addition**

```bash
git add .github/workflows/web.yml
git commit -m "ci: verify web application"
```

### Task 2: Атомарный старт обращения во frontend

**Files:**
- Modify: `apps/web/src/features/conversation/useConversation.ts`
- Modify: `apps/web/src/features/conversation/ConversationPage.tsx`
- Modify: `apps/web/src/features/conversation/useConversation.test.tsx`
- Modify: `apps/web/src/features/conversation/ConversationPage.test.tsx`
- Modify: `apps/web/package.json`

**Interfaces:**
- Consumes: `api.createConversation(): Promise<Conversation>` and `api.sendMessage(id, payload): Promise<Conversation>`.
- Produces: `startWithMessage(content: string): Promise<void>` in `ConversationState`; `start()` remains for an empty conversation retry; `npm test` invokes Vitest.

- [ ] **Step 1: Write a failing hook test for the first message**

Add to `useConversation.test.tsx`:

```tsx
it("creates a conversation and sends the first message with returned revision", async () => {
  const seen: unknown[] = [];
  server.use(
    http.post("*/api/conversations", () =>
      HttpResponse.json(makeConversation({ id: "fresh", revision: 4 }), { status: 201 }),
    ),
    http.post("*/api/conversations/fresh/messages", async ({ request }) => {
      seen.push(await request.json());
      return HttpResponse.json(makeConversation({
        id: "fresh",
        revision: 5,
        status: "CLARIFYING",
        messages: [makeMessage("user", "Не работает VPN")],
      }));
    }),
  );
  const { result } = renderHook(() => useConversation());
  await waitFor(() => expect(result.current.phase).toBe("ready"));

  await act(async () => result.current.startWithMessage("Не работает VPN"));

  expect(seen).toEqual([{ content: "Не работает VPN", expected_revision: 4 }]);
  expect(result.current.conversation?.revision).toBe(5);
});
```

- [ ] **Step 2: Run the test and confirm the missing method failure**

Run: `cd apps/web && npx vitest run src/features/conversation/useConversation.test.tsx`

Expected: FAIL because `startWithMessage` is absent.

- [ ] **Step 3: Implement `startWithMessage` using the create response directly**

In `useConversation.ts`, add the interface member and callback:

```tsx
const startWithMessage = useCallback(async (content: string) => {
  if (sending) return;
  setSending(true);
  setError(null);
  setPhase("loading");
  try {
    const created = await api.createConversation();
    storeId(created.id);
    const updated = await api.sendMessage(created.id, {
      content,
      expected_revision: created.revision,
    });
    setConversation(updated);
    setPhase("ready");
  } catch (err) {
    setError(describeError(err));
    setPhase("error");
    throw err;
  } finally {
    setSending(false);
  }
}, [sending]);
```

Return `startWithMessage` from the hook. In `ConversationPage.tsx`, replace the two-call welcome handler with `onSubmit={conv.startWithMessage}`.

- [ ] **Step 4: Add a page-level regression test**

Add a test that types into `Описание проблемы`, clicks `Отправить обращение`, and awaits the rendered user message. The MSW handler must assert the request path includes the newly created ID.

- [ ] **Step 5: Add the documented test script**

Update `apps/web/package.json`:

```json
"scripts": {
  "dev": "vite",
  "build": "tsc -b && vite build",
  "lint": "oxlint",
  "test": "vitest",
  "preview": "vite preview"
}
```

- [ ] **Step 6: Verify frontend**

Run:

```bash
cd apps/web
npm test -- --run
npm run lint
npm run build
```

Expected: all tests pass, lint has no errors, build succeeds.

- [ ] **Step 7: Commit**

```bash
git add apps/web
git commit -m "fix(web): preserve the first support message"
```

### Task 3: Типизированный поисковый корпус

**Files:**
- Create: `knowledge-base/articles/support_faq.yaml`
- Create: `services/ai/helpflow_ai/retrieval.py`
- Modify: `services/ai/helpflow_ai/schemas.py`
- Modify: `services/ai/helpflow_ai/knowledge.py`
- Create: `services/ai/tests/test_retrieval.py`

**Interfaces:**
- Consumes: existing `Playbook` objects and `knowledge-base/articles/*.yaml`.
- Produces: `KnowledgeChunk`, `KnowledgeMatch`, `KnowledgeRetriever.search(query: str, playbook_id: str | None, limit: int = 4) -> list[KnowledgeMatch]`; `KnowledgeBase.chunks`.

- [ ] **Step 1: Write failing schema and ranking tests**

Create `services/ai/tests/test_retrieval.py` with tests that assert:

```python
def test_vpn_query_returns_only_approved_chunks(kb):
    matches = KnowledgeRetriever(kb.chunks).search(
        "VPN пишет authentication failed", "vpn_connection"
    )
    assert matches
    assert matches[0].chunk.service == "VPN"
    assert all(match.chunk.id for match in matches)
    assert all(0.0 <= match.score <= 1.0 for match in matches)


def test_empty_and_unrelated_query_returns_no_confident_match(kb):
    retriever = KnowledgeRetriever(kb.chunks)
    assert retriever.search("", None) == []
    assert retriever.search("как приготовить борщ", "unknown") == []


def test_limit_and_ids_are_deterministic(kb):
    retriever = KnowledgeRetriever(kb.chunks)
    first = retriever.search("не подключается VPN", "vpn_connection", limit=3)
    second = retriever.search("не подключается VPN", "vpn_connection", limit=3)
    assert [m.chunk.id for m in first] == [m.chunk.id for m in second]
    assert len(first) <= 3
```

- [ ] **Step 2: Run tests and confirm import failures**

Run: `PYTHONPATH=services/ai .venv/bin/pytest services/ai/tests/test_retrieval.py -v`

Expected: FAIL because retrieval types do not exist.

- [ ] **Step 3: Add strict retrieval schemas**

Add to `schemas.py`:

```python
class KnowledgeChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    service: str
    title: str
    text: str
    keywords: list[str] = Field(default_factory=list)
    safety_notice: str | None = None
    escalation_team: str


class KnowledgeMatch(BaseModel):
    chunk: KnowledgeChunk
    score: float = Field(ge=0.0, le=1.0)
```

- [ ] **Step 4: Add approved FAQ entries**

Create `knowledge-base/articles/support_faq.yaml` as a list of ten entries with stable IDs:

```yaml
- id: vpn.authentication
  service: VPN
  title: Ошибка аутентификации VPN
  text: Проверьте корпоративный логин и актуальный пароль. Не сообщайте пароль помощнику или оператору.
  keywords: [vpn, authentication failed, аутентификация, пароль]
  safety_notice: Никому не сообщайте пароль или код подтверждения.
  escalation_team: Сетевые администраторы
- id: crm.access
  service: CRM
  title: CRM не открывается или не принимает учётные данные
  text: Проверьте подключение к корпоративной сети или VPN и запишите точный текст ошибки. Не повторяйте ввод пароля много раз, чтобы не заблокировать учётную запись.
  keywords: [crm, срм, вход, 403, сервер не найден]
  safety_notice: Не сообщайте пароль и код подтверждения.
  escalation_team: Команда CRM
- id: email.outlook
  service: Корпоративная почта
  title: Outlook не отправляет или не получает письма
  text: Проверьте интернет, статус подключения Outlook и наличие писем в папке Исходящие. Сохраните точный текст ошибки синхронизации.
  keywords: [outlook, почта, письмо, исходящие, синхронизация]
  escalation_team: Администраторы почты
- id: password.login
  service: Учётная запись
  title: Не удаётся войти с корпоративным паролем
  text: Проверьте раскладку клавиатуры и Caps Lock. Если пароль недавно менялся, используйте новый пароль и не пересылайте его другим людям.
  keywords: [пароль, логин, неверный пароль, учётная запись, вход]
  safety_notice: Никому не сообщайте пароль или одноразовый код.
  escalation_team: Управление учётными записями
- id: network.wifi
  service: Сеть/Wi-Fi
  title: Нет подключения к сети
  text: Проверьте, включён ли Wi-Fi, видна ли корпоративная сеть и открываются ли сайты через другую сеть. Запишите системное сообщение об ошибке.
  keywords: [wifi, wi-fi, сеть, интернет, нет подключения]
  escalation_team: Сетевые администраторы
- id: video.audio
  service: Видеосвязь
  title: Не работает звук или микрофон на встрече
  text: Проверьте выбранные в приложении микрофон и динамики и разрешение операционной системы на доступ к микрофону.
  keywords: [teams, zoom, видеозвонок, микрофон, звук, не слышат]
  escalation_team: Поддержка рабочих мест
- id: access.rights
  service: Права доступа
  title: Недостаточно прав для файла или системы
  text: Запишите название ресурса и текст отказа в доступе. Не пытайтесь обходить ограничения или использовать чужую учётную запись.
  keywords: [доступ, права, запрещено, access denied, 403]
  safety_notice: Не используйте чужие учётные данные и не обходите ограничения доступа.
  escalation_team: Управление доступом
- id: security.phishing
  service: Информационная безопасность
  title: Подозрительная ссылка или ввод данных на фишинговом сайте
  text: Не открывайте ссылку повторно. Если данные уже введены, отключите устройство от сети и немедленно передайте обращение информационной безопасности.
  keywords: [фишинг, подозрительная ссылка, ввёл пароль, вирус, шифрование]
  safety_notice: Не открывайте ссылку повторно и не удаляйте следы инцидента.
  escalation_team: Информационная безопасность
- id: service.outage
  service: Корпоративный сервис
  title: Сервис недоступен у нескольких сотрудников
  text: Зафиксируйте название сервиса, время начала, код ошибки и примерное число затронутых сотрудников. Не повторяйте одинаковую диагностику на каждом устройстве.
  keywords: [у всех, весь отдел, массовый сбой, 502, 503, недоступен]
  escalation_team: Service Desk Major Incident
- id: unknown.collect-context
  service: Не определён
  title: Недостаточно данных для безопасной инструкции
  text: Нужно уточнить название программы, наблюдаемое поведение, точный текст ошибки и время начала. Если сценарий не найден, обращение передаётся Service Desk L1 без догадок.
  keywords: [не работает, всё сломалось, ошибка, неизвестно]
  escalation_team: Service Desk L1
```

Every entry names an escalation team and contains no environment-specific credentials, server names or destructive commands.

- [ ] **Step 5: Load playbook steps and FAQ into chunks**

Extend `KnowledgeBase` so its constructor receives optional article chunks and `load()` appends playbook-derived chunks:

```python
class KnowledgeBase:
    def __init__(self, playbooks: list[Playbook], chunks: list[KnowledgeChunk] | None = None):
        # keep the existing duplicate and fallback validation
        self._playbooks = {playbook.id: playbook for playbook in playbooks}
        self._chunks = tuple(chunks or _playbook_chunks(playbooks))

    @property
    def chunks(self) -> list[KnowledgeChunk]:
        return list(self._chunks)
```

`load()` reads every `articles/*.yaml` list, validates each mapping as `KnowledgeChunk`, and combines it with `_playbook_chunks(playbooks)`. Use IDs `vpn_connection.question.error_text`, `vpn_connection.step.restart_vpn_client`, and `vpn_connection.safety` for playbook-derived fragments. Raise `KnowledgeBaseError` for duplicate chunk IDs or malformed article YAML; do not silently skip a file.

- [ ] **Step 6: Implement deterministic token scoring**

In `retrieval.py`, implement the deterministic scorer:

```python
TOKEN_RE = re.compile(r"[a-zа-яё0-9]+", re.IGNORECASE)
MIN_SCORE = 0.18


def _tokens(text: str) -> set[str]:
    return {token.casefold() for token in TOKEN_RE.findall(text)}


class KnowledgeRetriever:
    def __init__(self, chunks: list[KnowledgeChunk]):
        self._chunks = tuple(chunks)

    def search(self, query: str, playbook_id: str | None, limit: int = 4) -> list[KnowledgeMatch]:
        query_tokens = _tokens(query)
        if not query_tokens or limit < 1:
            return []
        matches = []
        for chunk in self._chunks:
            chunk_tokens = _tokens(" ".join([chunk.title, chunk.text, *chunk.keywords]))
            overlap = len(query_tokens & chunk_tokens) / len(query_tokens)
            prefix = f"{playbook_id}." if playbook_id else ""
            playbook_bonus = 0.30 if prefix and chunk.id.startswith(prefix) else 0.0
            score = min(1.0, overlap + playbook_bonus)
            if score >= MIN_SCORE:
                matches.append(KnowledgeMatch(chunk=chunk, score=score))
        return sorted(matches, key=lambda match: (-match.score, match.chunk.id))[:limit]
```

- [ ] **Step 7: Verify retrieval and all existing AI tests**

Run:

```bash
PYTHONPATH=services/ai .venv/bin/pytest services/ai/tests/test_retrieval.py -v
PYTHONPATH=services/ai .venv/bin/pytest services/ai/tests -q
```

Expected: new tests and all existing AI tests pass.

- [ ] **Step 8: Commit**

```bash
git add knowledge-base/articles services/ai/helpflow_ai services/ai/tests/test_retrieval.py
git commit -m "feat(ai): add approved knowledge retrieval"
```

### Task 4: Строгий контракт grounded-ответа

**Files:**
- Modify: `services/ai/helpflow_ai/schemas.py`
- Modify: `services/ai/helpflow_ai/prompts.py`
- Modify: `services/ai/helpflow_ai/engine.py`
- Modify: `services/ai/tests/test_llm.py`

**Interfaces:**
- Consumes: `KnowledgeRetriever.search` and deterministic `Decision`.
- Produces: `GroundedAnswer`; `Decision.source_ids`, `Decision.fallback_reason`, `Decision.llm_latency_ms`.

- [ ] **Step 1: Write failing grounded-output tests**

Add these tests, using the existing `fake_llm` helper:

```python
def test_grounded_reply_accepts_only_prompt_sources(kb):
    ctx = ConversationContext(original_request="Не работает VPN", playbook_id="vpn_connection")
    expected = TriageEngine(kb).decide(ctx)
    source_id = KnowledgeRetriever(kb.chunks).search(
        ctx.original_request, ctx.playbook_id
    )[0].chunk.id
    reply = {
        "answer": "Уточните, пожалуйста, точный текст ошибки VPN.",
        "source_ids": [source_id],
        "confidence": 0.91,
        "needs_operator": False,
        "reason": "Найден сценарий VPN",
    }
    result = TriageEngine(kb, fake_llm([reply])).decide(ctx)
    assert result.action == expected.action
    assert result.question == expected.question
    assert result.step == expected.step
    assert result.source_ids == [source_id]
    assert result.message_source == "llm"


def test_grounded_unknown_source_falls_back_to_rule_message(kb):
    ctx = ConversationContext(original_request="Не работает VPN", playbook_id="vpn_connection")
    expected = TriageEngine(kb).decide(ctx)
    reply = {
        "answer": "Перезагрузите сервер.",
        "source_ids": ["invented.source"],
        "confidence": 0.99,
        "needs_operator": False,
        "reason": "Источник якобы найден",
    }
    result = TriageEngine(kb, fake_llm([reply])).decide(ctx)
    assert result.message == expected.message
    assert result.message_source == "rules"
    assert result.fallback_reason == "unknown_source"


def test_grounded_low_confidence_falls_back_to_rules(kb):
    ctx = ConversationContext(original_request="Не работает VPN", playbook_id="vpn_connection")
    expected = TriageEngine(kb).decide(ctx)
    source_id = KnowledgeRetriever(kb.chunks).search(
        ctx.original_request, ctx.playbook_id
    )[0].chunk.id
    reply = {
        "answer": "Попробуйте снова.",
        "source_ids": [source_id],
        "confidence": 0.20,
        "needs_operator": False,
        "reason": "Недостаточно совпадений",
    }
    result = TriageEngine(kb, fake_llm([reply])).decide(ctx)
    assert result.message == expected.message
    assert result.fallback_reason == "low_confidence"


def test_grounded_smalltalk_intent_does_not_call_llm(kb):
    calls = []
    engine = TriageEngine(kb, fake_llm([], calls))
    assert engine.conversation_intent("Привет") == "greeting"
    assert engine.conversation_intent("Спасибо") == "thanks"
    assert calls == []
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `PYTHONPATH=services/ai .venv/bin/pytest services/ai/tests/test_llm.py -k grounded -v`

Expected: FAIL because grounded fields and prompt do not exist.

- [ ] **Step 3: Add strict models**

Add:

```python
class GroundedAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str = Field(min_length=1, max_length=1200)
    source_ids: list[str] = Field(min_length=1, max_length=4)
    confidence: float = Field(ge=0.0, le=1.0)
    needs_operator: bool
    reason: str = Field(min_length=1, max_length=300)
```

Extend `Decision`:

```python
source_ids: list[str] = Field(default_factory=list)
fallback_reason: str | None = None
llm_latency_ms: int | None = Field(default=None, ge=0)
```

- [ ] **Step 4: Replace the free rewrite prompt with a grounded prompt**

Replace `RESPONSE_SYSTEM` and add the builder:

```python
RESPONSE_SYSTEM = """Ты — помощник корпоративной технической поддержки.
Верни только JSON с ключами answer, source_ids, confidence, needs_operator, reason.
Не меняй prepared_action и не добавляй шаги, которых нет в prepared_message или sources.
source_ids могут содержать только id из sources.
needs_operator должен быть true только когда prepared_action равен escalate.
Не выдумывай факты, адреса серверов, учётные данные или настройки.
"""


def build_grounded_response_user(
    decision: Decision,
    playbook: Playbook,
    matches: list[KnowledgeMatch],
) -> str:
    payload = {
        "prepared_action": decision.action.value,
        "prepared_message": decision.message,
        "service": playbook.service,
        "safety_notice": playbook.safety_notice,
        "sources": [
            {"id": match.chunk.id, "title": match.chunk.title, "text": match.chunk.text}
            for match in matches
        ],
    }
    return f"<response_task>\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n</response_task>"
```

- [ ] **Step 5: Validate the candidate before copying text**

In `_render_decision`:

```python
matches = self.retriever.search(query, playbook.id)
if not matches:
    return decision.model_copy(update={"fallback_reason": "no_sources"})
started = time.monotonic()
raw = self.llm.chat_json(
    RESPONSE_SYSTEM,
    build_grounded_response_user(decision, playbook, matches),
)
answer = GroundedAnswer.model_validate(raw)
allowed = {match.chunk.id for match in matches}
if not set(answer.source_ids) <= allowed:
    return decision.model_copy(update={"fallback_reason": "unknown_source"})
if answer.confidence < 0.65:
    return decision.model_copy(update={"fallback_reason": "low_confidence"})
if answer.needs_operator != (decision.action == DecisionAction.ESCALATE):
    return decision.model_copy(update={"fallback_reason": "action_mismatch"})
```

Preserve the existing safety-notice check. On success set `message_source="llm"`, `source_ids`, and elapsed milliseconds. Map validation, transport and JSON failures to stable reasons without changing the selected action.

- [ ] **Step 6: Verify injection and safety regression tests**

Run:

```bash
PYTHONPATH=services/ai .venv/bin/pytest services/ai/tests/test_llm.py -v
PYTHONPATH=services/ai .venv/bin/pytest services/ai/tests/test_dialogue_flow.py -v
```

Expected: all tests pass; prompt-injection text is not included in the response prompt; security notice remains present.

- [ ] **Step 7: Commit**

```bash
git add services/ai/helpflow_ai services/ai/tests/test_llm.py
git commit -m "feat(ai): ground Ollama replies in approved sources"
```

### Task 5: Сохранение AI-происхождения и fallback в PostgreSQL

**Files:**
- Create: `apps/api/alembic/versions/20260926_0004_ai_provenance.py`
- Modify: `apps/api/app/models/conversation.py`
- Modify: `apps/api/app/schemas/conversation.py`
- Modify: `apps/api/app/services/triage.py`
- Modify: `apps/api/tests/test_migrations.py`
- Modify: `apps/api/tests/test_triage_integration.py`
- Modify: `apps/web/src/api/types.ts`
- Modify: `apps/web/src/test/fixtures.ts`
- Modify: `apps/web/src/features/operator/TicketDetail.tsx`

**Interfaces:**
- Consumes: `Decision.source_ids`, `fallback_reason`, `llm_latency_ms`.
- Produces in `ConversationRead`: `rag_source_ids: string[]`, `ai_fallback_reason: string | null`, `ai_latency_ms: number | null`.

- [ ] **Step 1: Write failing API persistence tests**

Add integration tests that inject decision metadata and reload from a new DB session:

```python
def test_ai_provenance_survives_database_reload(client, db_session, monkeypatch):
    from app.api.routes.conversations import get_triage_engine

    engine = get_triage_engine()
    original = engine.decide

    def grounded(context):
        return original(context).model_copy(update={
            "source_ids": ["vpn.authentication"],
            "fallback_reason": None,
            "llm_latency_ms": 321,
        })

    monkeypatch.setattr(engine, "decide", grounded)
    cid = client.post("/api/conversations").json()["id"]
    state = send(client, cid, "Не работает VPN")
    db_session.expunge_all()
    reloaded = client.get(f"/api/conversations/{cid}").json()
    assert reloaded["rag_source_ids"] == ["vpn.authentication"]
    assert reloaded["ai_fallback_reason"] is None
    assert reloaded["ai_latency_ms"] == 321
    assert reloaded["revision"] == state["revision"]


def test_ai_fallback_reason_is_persisted(client, monkeypatch):
    from app.api.routes.conversations import get_triage_engine

    engine = get_triage_engine()
    original = engine.decide

    def fallback(context):
        return original(context).model_copy(update={
            "source_ids": [],
            "fallback_reason": "low_confidence",
            "llm_latency_ms": 87,
        })

    monkeypatch.setattr(engine, "decide", fallback)
    cid = client.post("/api/conversations").json()["id"]
    state = send(client, cid, "Не работает VPN")
    assert state["rag_source_ids"] == []
    assert state["ai_fallback_reason"] == "low_confidence"
    assert state["ai_latency_ms"] == 87
```

- [ ] **Step 2: Run focused backend tests**

Run: `cd apps/api && ../../.venv/bin/pytest tests/test_triage_integration.py -k provenance -v`

Expected: FAIL because response fields do not exist.

- [ ] **Step 3: Add model fields and migration**

Model fields:

```python
rag_source_ids: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]")
ai_fallback_reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
ai_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
```

Migration `0004` adds the three columns with `rag_source_ids` non-null and default `[]`; downgrade removes only these columns.

- [ ] **Step 4: Expose typed API fields**

Add matching fields to `ConversationRead`, TypeScript `Conversation`, and fixtures. Keep defaults compatible with rows created before the migration.

- [ ] **Step 5: Persist metadata transactionally**

In `_advance`, after `decision = self.engine.decide(self._context(conversation))`, assign all three fields before appending the assistant message. A rule-only decision stores empty sources and its stable fallback reason; a successful grounded reply clears the previous fallback reason.

- [ ] **Step 6: Show operator-only provenance**

In `TicketDetail.tsx`, render a section `Источники ответа` when `rag_source_ids.length > 0`, and an operator-facing badge `Использован безопасный fallback` when `ai_fallback_reason` is set. Do not show internal reasons on the employee screen.

- [ ] **Step 7: Verify migrations, backend and frontend types**

Run:

```bash
cd apps/api
../../.venv/bin/pytest tests/test_migrations.py tests/test_triage_integration.py -v
cd ../web
npm test -- --run
npm run build
```

Expected: migration roundtrip and API tests pass; TypeScript build passes.

- [ ] **Step 8: Commit**

```bash
git add apps/api apps/web/src/api apps/web/src/test apps/web/src/features/operator
git commit -m "feat(api): persist grounded answer provenance"
```

### Task 6: Неизвестные запросы и fail-closed эскалация

**Files:**
- Modify: `services/ai/helpflow_ai/engine.py`
- Modify: `knowledge-base/playbooks/unknown.yaml`
- Modify: `services/ai/tests/test_dialogue_flow.py`
- Modify: `apps/api/tests/test_triage_integration.py`

**Interfaces:**
- Consumes: existing three-question cap, retrieval result and `DecisionAction.ESCALATE`.
- Produces: deterministic L1 escalation after exhausted unknown clarification; no generic technical step is invented for an unmatched request.

- [ ] **Step 1: Write a failing AI flow test**

```python
def test_unknown_issue_escalates_after_unique_clarifications(simulate):
    sim = simulate("У меня странная проблема, ничего не понятно")
    asked = []
    while sim.decision.action == DecisionAction.ASK:
        asked.append(sim.decision.question.fact)
        sim.answer("не знаю")
    assert asked == ["service_name", "error_text", "since_when"]
    assert sim.decision.action == DecisionAction.ESCALATE
    assert sim.decision.escalation_team == "Service Desk L1"
```

- [ ] **Step 2: Run the test and verify current generic-step failure**

Run: `PYTHONPATH=services/ai .venv/bin/pytest services/ai/tests/test_dialogue_flow.py -k unknown_issue -v`

Expected: FAIL because current unknown playbook returns `restart_app`.

- [ ] **Step 3: Make the unknown playbook fail closed after questions**

Remove generic troubleshooting steps from `unknown.yaml` and set `escalate_immediately: false`. Update `_decide_rules`: questions remain first; when the selected playbook is `unknown` and no unanswered question remains, return `_escalate(playbook, "не найден подтверждённый сценарий в базе знаний")`.

- [ ] **Step 4: Add an API test for the final operator card**

Drive three answers through `POST /messages`, assert `ESCALATED`, `recommended_team == "Service Desk L1"`, original request is preserved, and no completed step exists.

- [ ] **Step 5: Verify full AI and backend suites**

Run:

```bash
PYTHONPATH=services/ai .venv/bin/pytest services/ai/tests -q
cd apps/api && ../../.venv/bin/pytest -q
```

Expected: all tests pass, including the existing three-question maximum.

- [ ] **Step 6: Commit**

```bash
git add services/ai/helpflow_ai/engine.py knowledge-base/playbooks/unknown.yaml services/ai/tests apps/api/tests/test_triage_integration.py
git commit -m "feat(dialogue): escalate unsupported issues safely"
```

### Task 7: Пять сквозных сценариев и единый запуск

**Files:**
- Create: `apps/api/tests/test_p0_acceptance.py`
- Create: `scripts/smoke-p0.sh`
- Create: `scripts/smoke-p0.ps1`
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `.github/workflows/backend.yml`

**Interfaces:**
- Consumes: merged API/frontend, PostgreSQL migrations, Ollama settings and grounded metadata.
- Produces: reproducible P0 acceptance suite and equivalent macOS/Linux and Windows smoke commands.

- [ ] **Step 1: Add five acceptance tests**

Create `apps/api/tests/test_p0_acceptance.py` with a local helper and these concrete assertions:

```python
def send(client, cid, content):
    response = client.post(f"/api/conversations/{cid}/messages", json={"content": content})
    assert response.status_code == 200, response.text
    return response.json()


def test_crm_urgent_path_resolves(client):
    cid = client.post("/api/conversations").json()["id"]
    state = send(client, cid, "Не могу войти в CRM, через 20 минут встреча")
    assert state["urgency"] == "high"
    state = send(client, cid, "Ошибка соединения, VPN не подключён")
    assert state["status"] == "TROUBLESHOOTING"
    state = client.post(
        f"/api/conversations/{cid}/step-result", json={"outcome": "helped"}
    ).json()
    assert state["status"] == "VERIFYING"
    assert send(client, cid, "Да, доступ восстановился")["status"] == "RESOLVED"


def test_vpn_failed_steps_escalate_with_fallback_metadata(client):
    cid = client.post("/api/conversations").json()["id"]
    state = send(client, cid, "Не подключается VPN")
    while state["status"] == "CLARIFYING":
        state = send(client, cid, "не знаю")
    while state["status"] == "TROUBLESHOOTING":
        state = client.post(
            f"/api/conversations/{cid}/step-result", json={"outcome": "not_helped"}
        ).json()
    assert state["status"] == "ESCALATED"
    assert state["escalation_card"]["original_request"] == "Не подключается VPN"
    assert state["completed_steps"]
    assert isinstance(state["rag_source_ids"], list)


def test_phishing_escalates_without_dangerous_steps(client):
    cid = client.post("/api/conversations").json()["id"]
    state = send(client, cid, "Перешёл по фишинговой ссылке и ввёл пароль")
    assert state["status"] == "ESCALATED"
    assert state["completed_steps"] == []
    assert "Отключите" in state["messages"][-1]["content"]
    assert state["escalation_card"]["recommended_team"]


def test_unknown_issue_escalates_without_hallucinated_step(client):
    cid = client.post("/api/conversations").json()["id"]
    state = send(client, cid, "Происходит что-то странное")
    assistant_questions = []
    while state["status"] == "CLARIFYING":
        assistant_questions.append(state["messages"][-1]["content"])
        state = send(client, cid, "не знаю")
    assert state["status"] == "ESCALATED"
    assert len(assistant_questions) == len(set(assistant_questions)) == 3
    assert state["completed_steps"] == []
    assert state["escalation_card"]["recommended_team"] == "Service Desk L1"


def test_mass_outage_escalates_as_mass_incident(client):
    cid = client.post("/api/conversations").json()["id"]
    state = send(client, cid, "CRM не работает у всего отдела, у всех ошибка 502")
    if state["status"] == "CLARIFYING":
        state = send(client, cid, "весь отдел")
    assert state["status"] == "ESCALATED"
    assert state["playbook_id"] == "mass_incident"
    assert state["urgency"] == "critical"
    tickets = client.get("/api/operator/tickets").json()
    assert any(ticket["id"] == cid for ticket in tickets)
```

These tests assert final status, unique questions, completed steps, original request, operator visibility, and provenance/fallback fields. Ollama calls in lower-level AI tests use `httpx.MockTransport`; no CI test contacts the local machine.

- [ ] **Step 2: Run acceptance tests and close all failures**

Run: `cd apps/api && ../../.venv/bin/pytest tests/test_p0_acceptance.py -v`

Expected: five passing tests.

- [ ] **Step 3: Add platform-equivalent smoke scripts**

Both scripts must:

1. start `docker compose up -d --build`;
2. wait for `/health` with a bounded retry loop;
3. create a conversation;
4. send `Привет, не работает VPN`;
5. assert HTTP 200 and a non-empty assistant message;
6. print frontend and operator URLs.

The shell script uses `curl`; PowerShell uses `Invoke-RestMethod`. Neither script performs `docker compose down` automatically, so PostgreSQL data is not destroyed.

- [ ] **Step 4: Document exact Ollama and fallback modes**

`.env.example` must include:

```dotenv
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=qwen3.5:9b
AI_TIMEOUT_SECONDS=90
```

README must explain `AI_PROVIDER=rules` as the no-Ollama fallback and use `docker compose up -d --build` only from the repository root.

- [ ] **Step 5: Run complete verification**

Run:

```bash
cd apps/api && ../../.venv/bin/pytest -q
cd ../.. && PYTHONPATH=services/ai .venv/bin/pytest services/ai/tests -q
cd apps/web && npm test -- --run && npm run lint && npm run build
cd ../.. && docker compose up -d --build
./scripts/smoke-p0.sh
```

Expected: all automated tests pass; Compose reports healthy database and running API; smoke script completes successfully.

- [ ] **Step 6: Commit**

```bash
git add apps/api/tests/test_p0_acceptance.py scripts .env.example README.md .github/workflows/backend.yml
git commit -m "test(flow): verify P0 support scenarios"
```

### Task 8: Проверка ветки и подготовка следующего плана

**Files:**
- Modify: `PROJECT_PLAN.md`
- Create after P0 verification: `docs/superpowers/plans/2026-09-26-p1-incident-radar.md`

**Interfaces:**
- Consumes: полностью зелёную P0 ветку.
- Produces: зафиксированный статус P0 и отдельный исполнимый план Incident Radar без смешивания с RAG-изменениями.

- [ ] **Step 1: Record verified P0 status**

Update `PROJECT_PLAN.md` with exact test counts, commit SHA, supported run modes and remaining P1/P2 scope. Do not claim manual checks that were not run.

- [ ] **Step 2: Run diff and repository hygiene checks**

Run:

```bash
git status --short
git diff --check origin/develop HEAD
git log --oneline origin/develop..HEAD
```

Expected: no untracked runtime files, no whitespace errors, coherent task-sized commits.

- [ ] **Step 3: Commit status documentation**

```bash
git add PROJECT_PLAN.md
git commit -m "docs: record P0 integration status"
```

- [ ] **Step 4: Write the separate Incident Radar plan**

Use `superpowers:brainstorming` against the now-integrated repository, then `superpowers:writing-plans`. The plan must define the incident schema, similarity rule, confirmation workflow, endpoints, migrations, operator UI, tests and demo seed independently of this P0 plan.
