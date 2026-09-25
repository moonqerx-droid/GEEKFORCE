# GEEKFORCE HelpFlow

MVP виртуального помощника технической поддержки: управляемый диалог, пошаговая диагностика, проверка результата и передача обращения специалисту с сохранённым контекстом.

## Что уже реализовано

- FastAPI и интерактивная документация OpenAPI;
- SQLite-хранилище обращений, сообщений и выполненных шагов;
- Alembic-миграции для обновления постоянной базы;
- контролируемая backend state machine;
- интегрированный AI-модуль команды и 11 сценариев базы знаний;
- режим правил без внешних ключей и опциональный OpenAI-совместимый провайдер;
- срочный CRM-сценарий, немедленная эскалация ИБ и массового сбоя;
- атомарное сохранение хода диалога и восстановление контекста после перезапуска;
- карточка эскалации и операторская очередь;
- минимальный браузерный debug-интерфейс;
- pytest и GitHub Actions;
- одинаковый Docker-запуск на macOS и Windows.

## Быстрый запуск через Docker

Требуется Docker Desktop.

```bash
docker compose up --build
```

После запуска:

- debug-интерфейс: <http://localhost:8000/debug>;
- debug-очередь специалиста: <http://localhost:8000/debug/operator>;
- Swagger: <http://localhost:8000/docs>;
- health check: <http://localhost:8000/health>;
- OpenAPI JSON: <http://localhost:8000/openapi.json>.

Остановить приложение:

```bash
docker compose down
```

Данные SQLite сохраняются в Docker volume `helpflow-data`.

## Локальный запуск на macOS

Из корня репозитория:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r apps/api/requirements.txt
pip install -e services/ai
cd apps/api
alembic upgrade head
uvicorn app.main:app --reload
```

## Локальный запуск на Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r apps/api/requirements.txt
pip install -e services/ai
Set-Location apps/api
alembic upgrade head
uvicorn app.main:app --reload
```

Если PowerShell запрещает активацию скрипта, один раз выполните:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## Локальный запуск на Windows cmd.exe

```bat
py -3.12 -m venv .venv
.venv\Scripts\activate.bat
pip install -r apps\api\requirements.txt
pip install -e services/ai
cd apps\api
alembic upgrade head
uvicorn app.main:app --reload
```

## Тестирование

macOS/Linux из корня репозитория:

```bash
cd apps/api
../../.venv/bin/pytest -v
```

Windows PowerShell с активированным окружением:

```powershell
Set-Location apps/api
pytest -v
```

## Миграции базы данных

В Docker миграции применяются автоматически перед запуском API. При локальной разработке из `apps/api`:

```bash
alembic upgrade head
```

Откатить последнюю миграцию:

```bash
alembic downgrade -1
```

## Основной API

```text
POST /api/conversations
GET  /api/conversations/{id}
POST /api/conversations/{id}/messages
POST /api/conversations/{id}/step-result
POST /api/conversations/{id}/escalate
GET  /api/operator/tickets
```

Полные схемы запросов и ответов всегда доступны в `/docs` и `/openapi.json`.

Для локального React/Next.js/Vite-фронтенда разрешены origin-порты `3000` и `5173`. Список настраивается переменной `CORS_ORIGINS` в JSON-формате.

## AI и совместимость

Новые обращения используют `services/ai/helpflow_ai`: вопросы, шаги и карточки берутся из `knowledge-base`. По умолчанию `AI_PROVIDER=mock` включает правила без сетевых запросов. Для LLM в Docker задайте `AI_PROVIDER=openai`, `AI_API_KEY`, при необходимости `AI_BASE_URL`, `AI_MODEL`, `AI_TIMEOUT_SECONDS` в корневом `.env`, затем пересоздайте сервис. Не добавляйте файл с ключами в Git.

Существующие обращения сохраняют прежнюю логику через `workflow_version=legacy`. Новые получают `triage-v1`. HTTP-контракт сохраняет значения `normal` и `cannot_perform`; адаптер переводит их в AI-значения `medium` и `cannot_do`. В ответ добавлена `escalation_card` с причиной передачи, командой, вопросами, шагами и текущим результатом.

В standalone-запуске AI читает настройки из переменных окружения процесса; `.env` автоматически подставляет Docker Compose. Подробности модуля — в [services/ai/README.md](services/ai/README.md). Проверка AI: `pytest services/ai/tests` из корня после `pip install -e services/ai`.

Debug UI и операторская очередь предназначены для локального демо команды. Аутентификация и ограничение доступа оператора пока не реализованы.

Результаты изучения веток команды и точки интеграции — в [docs/integration-status.md](docs/integration-status.md).

## Командная работа

Общий продуктовый план находится в [PROJECT_PLAN.md](PROJECT_PLAN.md). Контракты backend считаются публичным интерфейсом команды; изменения endpoint или схемы ответа согласовываются до merge.
