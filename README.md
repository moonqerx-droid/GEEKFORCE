# GEEKFORCE HelpFlow

AI-помощник технической поддержки, который превращает эмоциональное обращение сотрудника в управляемый процесс решения проблемы.

> Мы автоматизировали не ответ на вопрос, а весь путь обращения: от эмоционального описания до подтверждённого решения или передачи специалисту с полностью подготовленным контекстом.

## Что это

Пользователь описывает проблему свободным текстом. Система:

1. понимает суть, сервис, симптомы и обстоятельства;
2. определяет срочность и объясняет её причину;
3. задаёт только необходимые уточняющие вопросы;
4. предлагает действия по одному шагу;
5. после каждого шага узнаёт результат и выбирает продолжение;
6. подтверждает, что проблема решена;
7. при необходимости передаёт специалисту готовую карточку со всем контекстом.

## Архитектура репозитория

```text
GEEKFORCE/
├── apps/
│   ├── web/                 # интерфейс сотрудника
│   ├── operator/            # панель специалиста
│   └── api/                 # основное API (FastAPI)
├── services/
│   ├── ai/                  # анализ, вопросы, рекомендации
│   └── incidents/           # поиск похожих обращений
├── packages/
│   ├── contracts/           # общие API-типы и схемы
│   └── ui/                  # общие UI-компоненты
├── knowledge-base/
│   ├── playbooks/           # сценарии диагностики
│   └── test-cases/          # контрольные обращения
├── docs/
│   ├── architecture.md
│   ├── api-contract.md
│   ├── demo-script.md
│   └── integration-guide.md
├── .github/workflows/
├── docker-compose.yml
├── .env.example
├── README.md
└── PROJECT_PLAN.md
```

## Стек

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2, Pydantic 2, SQLite, Alembic
- **AI:** OpenAI-compatible LLM API + mock fallback без внешнего ключа
- **Incident Radar:** embeddings либо простой similarity search
- **Frontend / Operator:** решение команды (React/Next.js или vanilla — фиксируется отдельно)
- **Инфраструктура:** Docker Compose
- **CI:** GitHub Actions

## Быстрый старт

### Docker (рекомендуется)

```
cp .env.example .env
docker compose up --build
```

После запуска:

- API: http://localhost:8000
- Swagger: http://localhost:8000/docs
- Debug UI (бэкенд): http://localhost:8000/debug
- Operator UI: http://localhost:3000 (заглушка)

### Локально без Docker

Backend:

```
cd apps/api
python3.12 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Тесты

```
cd apps/api
pytest -v
```

## Ветки и PR

Схема веток:

```
main
└── develop
    ├── feat/user-interface
    ├── feat/backend-workflow
    ├── feat/ai-triage
    └── feat/operator-incidents
```

Правила — в CONTRIBUTING.md.

## Документация

- PROJECT_PLAN.md — главный документ команды
- [docs/architecture.md](https://docs/architecture.md) — схема компонентов
- [docs/api-contract.md](https://docs/api-contract.md) — API-контракты
- [docs/demo-script.md](https://docs/demo-script.md) — сценарий защиты
- [docs/integration-guide.md](https://docs/integration-guide.md) — как интегрировать части

## Роли

| Участник ↕▾ | Зона ↕▾ | Ветка ↕▾ |
|---|---|---|
| −1 | apps/web | feat/user-interface |
| 2 | apps/api, packages/contracts | feat/backend-workflow |
| 3 | services/ai, knowledge-base | feat/ai-triage |
| 4 | apps/operator, services/incidents, .github, docs, deploy | feat/operator-incidents |
⚙

</BDS:create_file>

<BDS:create_file fileName="CONTRIBUTING.md">

```markdown
# Правила работы с репозиторием

## Ветки

```text
main
└── develop
    ├── feat/user-interface
    ├── feat/backend-workflow
    ├── feat/ai-triage
    └── feat/operator-incidents

- Никто не пушит напрямую в `main`.
- Все feature-ветки ответвляются от `develop`.
- В `main` вливается только проверенная `develop`.
- Ветки обновляются из `develop` минимум два раза в день.

## Pull Requests

- Один PR решает одну законченную задачу.
- PR создаётся сразу в режиме Draft.
- Каждый PR проверяет хотя бы один участник.
- Участники не изменяют чужие каталоги без согласования.
- Общие типы (`packages/contracts`) изменяются отдельным PR ответственным за backend.

## Коммиты

Формат:

```
feat(chat): add troubleshooting step card
feat(ai): extract urgency from free-form request
fix(api): preserve completed troubleshooting steps
test(flow): cover urgent unresolved request
docs(plan): update team responsibilities
build(api): add cross-platform Docker workflow
```

Типы: `feat`, `fix`, `test`, `docs`, `build`, `chore`, `refactor`.

## Владение каталогами

| Каталог ↕▾ | Владелец ↕▾ |
|---|---|
| −`apps/web` | Участник 1 |
| −`apps/api`, `packages/contracts` | Участник 2 |
| `services/ai`, `knowledge-base` | Участник 3 |
| `apps/operator`, `services/incidents`, `.github`, `docs`, `docker-compose.yml` | Участник 4 |
⚙

## Feature freeze

За 3–4 часа до защиты вводится feature freeze. После него разрешены только исправления и улучшения демонстрации.

## Ежедневный синк

Два раза в день, максимум 10 минут. Каждый отвечает:

1. Что уже работает в продукте?
2. Что будет готово к следующей интеграции?
3. Что блокирует работу?
4. Какой PR требуется проверить?

После синка ответственный за интеграцию (Участник 4) обновляет issues и собирает `develop`.

</BDS:create_file>

<BDS:create_file fileName=".gitignore">

```gitignore
# Python
__pycache__/
*.py[cod]
*.egg-info/
.venv/
venv/
.pytest_cache/
.mypy_cache/
.ruff_cache/
*.db
*.sqlite
*.sqlite3

# Node
node_modules/
dist/
build/
.next/
.nuxt/
*.log
npm-debug.log*
yarn-error.log*

# Env
.env
.env.local
.env.*.local

# IDE
.vscode/
.idea/
*.swp
*.swo
.DS_Store

# Docker
.docker/

