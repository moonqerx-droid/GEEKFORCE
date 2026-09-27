# HelpFlow — веб-интерфейс (`apps/web`)

React + TypeScript + Vite фронтенд поверх backend из `origin/feat/backend-workflow`.
Два маршрута: `/` — интерфейс сотрудника, `/operator` — панель специалиста.

## Стек

- React 19 + TypeScript, Vite;
- React Router (`/`, `/operator`);
- обычный CSS с дизайн-токенами через CSS variables (`src/styles/tokens.css`);
- Vitest + React Testing Library + MSW для тестов;
- `lucide-react` при необходимости иконок.

## Запуск

Нужен запущенный backend (см. корневой `README.md`, ветка `feat/backend-workflow`):
он поднимается через `docker compose up --build` в отдельном worktree/checkout.

### macOS / Linux

```bash
cd apps/web
cp .env.example .env
npm install
npm run dev
```

### Windows PowerShell

```powershell
Set-Location apps/web
Copy-Item .env.example .env
npm install
npm run dev
```

Frontend поднимется на `http://localhost:5174`. Оставьте `VITE_API_BASE_URL`
пустым: Vite перенаправит `/api` и `/health` на backend на порту 8000.
Это работает и при занятом порте 5173. Для production нужен такой же reverse proxy
либо явный URL API с разрешённым CORS origin.

Отправка ограничена 12 секундами, ошибки показываются над формой, черновик
сохраняется при неудаче. Enter отправляет сообщение, Shift+Enter добавляет строку.

### Docker backend + Vite frontend одновременно

```bash
git worktree add ../GEEKFORCE-api origin/feat/backend-workflow
cd ../GEEKFORCE-api && docker compose up --build -d
cd ../GEEKFORCE/apps/web && npm run dev
```

## Тесты, сборка, lint

```bash
npm test -- --run
npm run build
npm run lint
```

Текущий статус (локально, на этой ветке): 18/18 тестов зелёные, production build
проходит, `npm run lint` — 0 ошибок (2 предупреждения `react/set-state-in-effect`
от oxlint на стандартном паттерне "fetch on mount" — эффект вызывает
async-функцию, а не синхронный `setState`, это ожидаемо).

Тесты используют MSW (`src/test/server.ts`) — обращения к реальному API не
выполняются.

## Архитектура

```text
src/
├── api/            # client.ts (единая точка fetch), types.ts, errors.ts
├── components/     # Button, Card/Badge/Spinner/EmptyState/ErrorState, Header, DebugPanel
├── features/
│   ├── conversation/   # useConversation, ConversationPage и вложенные экраны
│   └── operator/       # useOperatorTickets, OperatorPage и вложенные экраны
├── pages/          # тонкие обёртки над features для роутинга
├── styles/         # tokens.css (дизайн-токены), global.css (сброс, фокус, reduced-motion)
└── test/           # setup.ts, server.ts (MSW), fixtures.ts
```

Источник истины — последний объект `Conversation`, полученный от backend.
Клиентская state machine не дублируется: UI просто рендерит текущий `status`.

`useConversation`:

- восстанавливает активный диалог из `localStorage` (`helpflow.conversationId`)
  через `GET /api/conversations/{id}`; если backend не знает такой id (404),
  тихо сбрасывает и показывает экран начала обращения;
- всегда отправляет `expected_revision` из последнего ответа;
- при `409` не повторяет запрос автоматически: перечитывает состояние через
  `GET`, показывает баннер «Обращение изменилось в другой вкладке…» и не
  теряет черновик пользователя (текст остаётся в поле ввода);
- блокирует повторное нажатие кнопок на время запроса (`sending`).

## Известные ограничения и расхождения с исходным описанием

- `GET /api/operator/incidents` в `feat/backend-workflow` пока не существует
  (Incident Radar ещё проектируется — см. `PROJECT_PLAN.md`). Секция Incident
  Radar в `/operator` (`IncidentsSection`) вызывает этот endpoint и **тихо
  скрывается** при `404`. В production-коде фиктивные инциденты не
  подставляются; в тестах используются fixtures (`src/test/fixtures.ts`).
- `escalation_card` не имеет фиксированной схемы на бэкенде
  (`dict[str, unknown] | None` в `ConversationRead`), поэтому UI читает из
  него только опциональное поле `team` для отображения «кому передано» и
  корректно работает при `escalation_card: null`.
- Ручная browser-проверка полного сценария (срочная проблема → уточнение →
  шаг → helped → RESOLVED; несколько отрицательных исходов → ESCALATED →
  карточка в `/operator`; восстановление после перезагрузки; два таба и 409;
  375px/1440px viewport) не проводилась в этой сессии — здесь нет запущенного
  backend. Список сценариев для ручной проверки — в `FRONTEND_AGENT_PROMPT.md`
  в корне репозитория.
- Автоматическое обновление очереди `/operator` — раз в 15 секунд, только
  пока вкладка видима (`document.visibilityState`).

## Definition of Done — что сделано

- [x] `/` и `/operator` реализованы поверх реального API-контракта
      (`apps/api/app/schemas/conversation.py`, `routes/conversations.py`,
      `routes/operator.py` на `origin/feat/backend-workflow`);
- [x] весь обязательный сценарий проходим через UI (без raw JSON для
      пользователя — `playbook_id`/`confidence`/коды шагов только в
      `DebugPanel` за `VITE_SHOW_DEBUG=true`);
- [x] состояния загрузки/ошибки/409 обработаны;
- [x] адаптивность 375 / 768 / 1440 px, видимый focus, `aria-live` на новых
      сообщениях и уведомлениях, `prefers-reduced-motion`;
- [x] тесты, lint, production build — зелёные (см. выше);
- [x] изменения только в `apps/web/**` и этом файле.
- [ ] Ручная browser-проверка с реальным backend — не проводилась (нет
      поднятого backend в этой сессии), см. ограничения выше.
