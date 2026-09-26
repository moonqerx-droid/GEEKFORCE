# Промпт для frontend-агента

Скопируйте весь блок ниже в новую сессию другой нейросети. Агент должен иметь доступ к Git и репозиторию.

---

Ты — senior frontend-разработчик и product designer команды GEEKFORCE на хакатоне. Твоя задача — самостоятельно реализовать законченный, визуально сильный web-интерфейс HelpFlow поверх уже работающего backend. Не ограничивайся планом или макетом: пиши код, запускай его, проверяй тестами и браузером, коммить и пушь результат в GitHub.

## Контекст продукта

HelpFlow — AI-помощник внутренней технической поддержки. Пользователь описывает проблему обычным языком. Backend определяет сервис и срочность, задаёт уточняющие вопросы, выдаёт инструкции по одному шагу, проверяет результат и при необходимости передаёт специалисту полную карточку контекста.

Главная фраза продукта для защиты:

> Мы автоматизировали не ответ на вопрос, а весь путь обращения: от эмоционального описания до подтверждённого решения или передачи специалисту с полностью подготовленным контекстом.

Репозиторий: `https://github.com/moonqerx-droid/GEEKFORCE`

Backend PR: `https://github.com/moonqerx-droid/GEEKFORCE/pull/3`  
Backend-ветка с актуальным контрактом: `origin/feat/backend-workflow`  
Твоя ветка: `frontend`

## Git и параллельная работа

1. Клонируй репозиторий или открой существующий checkout.
2. Выполни `git fetch origin --prune`.
3. Переключись на `frontend`: `git switch frontend` и `git pull --ff-only origin frontend`.
4. Не сливай backend-ветку во frontend и не копируй backend-коммиты.
5. Для чтения актуальных файлов используй `git show origin/feat/backend-workflow:<path>`.
6. Для запуска API создай отдельный worktree: `git worktree add ../GEEKFORCE-api origin/feat/backend-workflow`. В нём выполни `docker compose up --build -d`.
7. В своей ветке изменяй только `apps/web/**` и, если действительно нужно, `docs/frontend/**`. Не меняй `apps/api`, `services/ai`, миграции, root `docker-compose.yml`, GitHub Actions и API-контракт.
8. Делай небольшие осмысленные коммиты. В конце пушь: `git push origin frontend`.
9. PR в `develop` создавай после merge backend PR №3 либо предварительно перебазируй frontend на обновлённый `origin/develop`, чтобы PR содержал только frontend-файлы.

Если `../GEEKFORCE-api` уже существует, не удаляй его: найди существующий worktree через `git worktree list` и используй его.

## Технический стек

Создай `apps/web` как:

- React + TypeScript + Vite;
- React Router для `/` и `/operator`;
- обычный CSS или CSS Modules с дизайн-токенами через CSS variables;
- Vitest + React Testing Library;
- минимум зависимостей; иконки можно взять из `lucide-react`;
- API base URL: `VITE_API_BASE_URL`, по умолчанию пустая строка для same-origin или `http://localhost:8000` в локальном `.env.example`;
- frontend dev server: `http://localhost:5173` — этот origin уже разрешён backend.

Не используй Next.js: для хакатона статическая Vite-сборка проще, быстрее и одинаково работает на macOS/Windows. Не делай нативное приложение. Это responsive web app, который можно открыть на ноутбуке или телефоне.

## Сначала изучи источники истины

Перед кодом полностью прочитай:

- `PROJECT_PLAN.md`;
- `README.md` из `origin/feat/backend-workflow`;
- `apps/api/app/schemas/conversation.py`;
- `apps/api/app/api/routes/conversations.py`;
- `apps/api/app/api/routes/operator.py`;
- `docs/integration-status.md`;
- `docs/superpowers/specs/2026-09-26-incident-radar-design.md`.

Получай OpenAPI из работающего backend: `http://localhost:8000/openapi.json`. Не выдумывай endpoints или поля.

## Текущий API-контракт

Основные endpoints:

```text
POST /api/conversations
GET  /api/conversations/{id}
POST /api/conversations/{id}/messages
POST /api/conversations/{id}/step-result
POST /api/conversations/{id}/escalate
GET  /api/operator/tickets
GET  /health
```

Создание сообщения:

```json
{
  "content": "Не могу войти в CRM, через 20 минут встреча",
  "expected_revision": 1
}
```

Результат шага:

```json
{
  "outcome": "helped",
  "expected_revision": 3,
  "step_code": "clear_crm_cookies"
}
```

Допустимые `outcome`: `helped`, `not_helped`, `cannot_perform`.

Статусы:

```text
NEW → CLARIFYING → TROUBLESHOOTING → VERIFYING → RESOLVED
                                             ↘ ESCALATED
```

Фактические переходы определяет backend. Frontend не должен вычислять следующий статус самостоятельно.

Ключевые поля ответа:

```ts
type ConversationStatus =
  | "NEW" | "ANALYZING" | "CLARIFYING"
  | "TROUBLESHOOTING" | "VERIFYING"
  | "RESOLVED" | "ESCALATED";

type Urgency = "low" | "normal" | "high" | "critical";

interface Conversation {
  id: string;
  revision: number;
  status: ConversationStatus;
  summary: string | null;
  service: string | null;
  symptoms: string[];
  urgency: Urgency;
  urgency_reason: string | null;
  known_facts: Record<string, string>;
  missing_facts: string[];
  confidence: number | null;
  playbook_id: string | null;
  messages: Array<{
    id: number;
    role: "user" | "assistant" | "system";
    content: string;
    created_at: string;
  }>;
  completed_steps: Array<{
    id: number;
    code: string;
    instruction: string;
    outcome: "helped" | "not_helped" | "cannot_perform";
    position: number;
    created_at: string;
  }>;
  current_step: { code: string; instruction: string } | null;
  escalation_summary: string | null;
  escalation_card: Record<string, unknown> | null;
  incident_id: string | null;
}
```

Всегда отправляй `expected_revision` из последнего ответа. Для результата шага также отправляй текущий `step_code`. При `409 Conflict`:

1. не повторяй mutation автоматически;
2. выполни `GET /api/conversations/{id}`;
3. обнови UI;
4. покажи понятное уведомление: «Обращение изменилось в другой вкладке. Мы загрузили актуальное состояние»;
5. не очищай набранный пользователем текст.

Блокируй повторное нажатие кнопки, пока запрос выполняется. После успешной отправки замени локальное состояние полным ответом backend.

## Что реализовать

### 1. Интерфейс сотрудника `/`

Сделай основной экран продуктовым, а не отладочным:

- компактный header с названием HelpFlow и индикатором состояния API;
- приветственный экран с одной ясной фразой и примерами обращений-кнопок;
- чат с визуально разными сообщениями пользователя и помощника;
- автоскролл и время сообщений;
- статус обращения на человеческом русском языке;
- карточка срочности с объяснением `urgency_reason`;
- карточка текущего шага только в `TROUBLESHOOTING`;
- три крупные кнопки: «Помогло», «Не помогло», «Не могу выполнить»;
- отдельный экран/баннер подтверждения в `VERIFYING`;
- финальный экран `RESOLVED` с выполненными шагами;
- экран `ESCALATED`: кому передано, причина, что уже приложено к обращению; используй `escalation_card`, но корректно работай и при `null`;
- кнопка ручной передачи специалисту до терминального статуса;
- возможность начать новое обращение;
- сохранение ID активного диалога в `localStorage` и восстановление через GET после перезагрузки;
- кнопка «Начать заново», которая создаёт новый диалог, не удаляя старый на сервере.

Не показывай пользователю сырой JSON, `playbook_id`, confidence или технические коды шагов. Их можно показать только в скрываемой dev-панели, включённой через `VITE_SHOW_DEBUG=true`.

### 2. Панель специалиста `/operator`

- очередь из `GET /api/operator/tickets`;
- сортировка уже приходит с backend, не меняй её незаметно;
- фильтры в UI: срочность, сервис, поиск по тексту;
- список слева, выбранная карточка справа на desktop; последовательные экраны на mobile;
- в карточке: исходное обращение, срочность и причина, известные факты, история вопросов, выполненные шаги и результаты, текущее резюме;
- понятные русские подписи для `helped`, `not_helped`, `cannot_perform`;
- индикатор `incident_id`, если он есть;
- ручное обновление и автоматическое обновление раз в 15 секунд только пока вкладка видима;
- корректные empty/loading/error states.

Incident Radar backend ещё проектируется. Подготовь отдельный компонент секции, но показывай его только если `GET /api/operator/incidents` реально отвечает `200`. При `404` тихо скрывай секцию. Не подставляй фиктивные инциденты в production UI. В тестах разрешены fixtures.

### 3. Дизайн

Нужен убедительный интерфейс B2B-продукта для защиты:

- спокойный светлый фон, тёмный графитовый текст, один насыщенный сине-фиолетовый акцент;
- семантические цвета срочности, не полагайся только на цвет — добавляй текст/иконку;
- хорошая типографика и плотность, похожая на современный support cockpit;
- карточки с тонкими границами, умеренными радиусами и ясной иерархией;
- никаких стоковых фото, гигантских градиентов, glassmorphism и декоративной перегрузки;
- адаптивность минимум для 375 px, 768 px и 1440 px;
- видимый focus, управление клавиатурой, `aria-live` для новых сообщений и ошибок;
- `prefers-reduced-motion`;
- WCAG AA для основного текста и кнопок.

Интерфейс полностью на русском языке. Названия типов и код — на английском.

### 4. Архитектура frontend

Раздели минимум так:

```text
apps/web/src/
├── api/            # client, errors, generated/handwritten types
├── components/     # reusable UI
├── features/
│   ├── conversation/
│   └── operator/
├── pages/
├── styles/
└── test/
```

Один API client отвечает за base URL, JSON, `409`, `422`, offline/network errors и AbortController. Не размазывай `fetch` по компонентам.

Не дублируй состояние backend в сложной клиентской state machine. Источник истины — последний объект `Conversation`.

## Тесты

Обязательные automated tests:

- API client формирует `expected_revision` и `step_code`;
- `409` загружает актуальный диалог и сохраняет draft;
- кнопки результата доступны только в `TROUBLESHOOTING`;
- поле сообщения доступно только в `NEW`, `CLARIFYING`, `VERIFYING`;
- терминальные статусы отключают mutations;
- восстановление разговора из `localStorage`;
- операторская очередь показывает эскалацию и выполненные шаги;
- empty/error/loading states;
- production build проходит.

Используй MSW либо небольшой контролируемый `fetch` stub для frontend-тестов. Не обращайся к реальному API из unit tests.

После unit tests обязательно проведи ручную browser-проверку с настоящим backend:

1. срочная проблема CRM → уточнение → шаг → helped → подтверждение → RESOLVED;
2. несколько неуспешных шагов → ESCALATED → карточка в `/operator`;
3. фишинговая ссылка → немедленная критическая эскалация;
4. перезагрузка страницы восстанавливает диалог;
5. две вкладки: устаревшая mutation получает 409 и восстанавливается без потери draft;
6. mobile viewport 375 px и desktop 1440 px;
7. в консоли браузера нет ошибок.

## Документация и Definition of Done

Добавь `apps/web/README.md` с командами macOS, Windows PowerShell и Docker-backend + Vite frontend.

Перед завершением выполни и приложи результаты:

```bash
npm test -- --run
npm run build
npm run lint
```

Definition of Done:

- `/` и `/operator` работают с реальным API;
- весь обязательный сценарий можно пройти без devtools;
- нет выдуманных API-полей;
- состояния загрузки, ошибки и 409 обработаны;
- layout адаптивен и доступен с клавиатуры;
- тесты, lint и production build зелёные;
- изменения находятся только в разрешённых frontend-путях;
- ветка `frontend` запушена в GitHub;
- в финальном сообщении перечислены коммиты, проверки, известные ограничения и точные URL локального запуска.

Не останавливайся на плане и не проси подтверждения рутинных решений. Если API отличается от этого описания, доверяй `/openapi.json` и файлам backend-ветки, зафиксируй расхождение в `apps/web/README.md` и адаптируй frontend без изменения backend.

---

## Как запустить параллельно

1. Откройте новую задачу/сессию нейросети с доступом к терминалу и GitHub.
2. Вставьте весь промпт выше.
3. Дайте ей рабочую папку с репозиторием или разрешите клонирование.
4. Backend оставьте запущенным на `http://localhost:8000`.
5. Frontend должен запуститься на `http://localhost:5173`.
6. Проверяйте работу агента в ветке `frontend`; backend продолжает жить в `feat/backend-workflow` и PR №3.
