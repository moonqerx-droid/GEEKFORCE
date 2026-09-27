# GEEKFORCE HelpFlow

MVP виртуального помощника технической поддержки: управляемый диалог, пошаговая диагностика, проверка результата и передача обращения специалисту с сохранённым контекстом.

## Что уже реализовано

- FastAPI и интерактивная документация OpenAPI;
- PostgreSQL-хранилище в командном Docker-окружении и SQLite для быстрых локальных тестов;
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

## Роли и демо

HelpFlow работает для трёх ролей:

- **Сотрудник** описывает проблему своими словами, проходит вопросы и шаги, видит «Карточку обращения» — что понял помощник. Если нужен человек, специалист подключается в тот же чат, сотрудник ничего не пересказывает и в конце ставит оценку.
- **Специалист поддержки** работает в очереди: срочные наверху, у каждого обращения готовая карточка от помощника (исходные слова, факты, вопросы и ответы, выполненные шаги, причина передачи). Берёт обращение, отвечает, закрывает с итогом.
- **Руководитель поддержки** видит метрики (доля решённых без специалиста, время до решения и до первого ответа, оценки, темы обращений и где помощник чаще передаёт людям, нагрузка команды) и приглашает специалистов.

Сотрудники регистрируются сами. Специалистов приглашает только руководитель: ссылка из раздела «Команда» (и письмо, если настроен SMTP). Первого руководителя задают `ADMIN_EMAIL` и `ADMIN_PASSWORD` в `.env`.

Демо-данные — аккаунты всех ролей и две недели истории, проигранной через настоящий движок:

```bash
docker compose exec api python -m app.seed_demo
```

Пароль всех демо-аккаунтов `DemoPass123`: `admin@helpflow.demo` (руководитель), `anna@helpflow.demo` и `oleg@helpflow.demo` (специалисты), `ivan@helpflow.demo` и ещё четверо сотрудников. В `npm run dev` на странице входа есть кнопки быстрого входа под каждой ролью.

## Быстрый запуск через Docker

Требуется Docker Desktop.

```bash
docker compose up -d --build
```

Команду выполняйте из корня репозитория. Проверить полный P0-сценарий после запуска:

```bash
./scripts/smoke-p0.sh
```

В Windows PowerShell используйте `./scripts/smoke-p0.ps1`.

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

Данные PostgreSQL сохраняются в Docker volume `helpflow-postgres-data`. При первом запуске Compose создаёт базу `helpflow`, применяет Alembic-миграции и только затем запускает API.

### Настройка писем через Яндекс Почту

Регистрация и восстановление пароля используют настоящий SMTP. Для локального MVP:

1. включите двухфакторную аутентификацию в Яндекс ID;
2. создайте отдельный пароль приложения для почты;
3. скопируйте `.env.example` в `.env`;
4. заполните `SMTP_USERNAME`, `SMTP_PASSWORD` и `SMTP_FROM_EMAIL`;
5. оставьте `SMTP_HOST=smtp.yandex.ru`, `SMTP_PORT=465`, `SMTP_SECURITY=ssl`;
6. задайте `APP_PUBLIC_URL` адресом frontend-приложения, например `http://localhost:5174`.

Обычный пароль от Яндекс ID использовать нельзя. Файл `.env` исключён из Git; не вставляйте почтовый пароль в исходный код, Dockerfile или команду запуска. Для production укажите HTTPS-адрес приложения и `COOKIE_SECURE=true`.

После регистрации HelpFlow отправляет письмо подтверждения. Ссылки подтверждения и сброса пароля одноразовые и ограничены по времени. Если SMTP временно недоступен, аккаунт сохраняется, а письмо можно запросить повторно.

Для командной разработки достаточно одинаковой команды на macOS и Windows. При необходимости скопируйте `.env.example` в `.env` и замените `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` и `DATABASE_URL` согласованно. Значения по умолчанию предназначены только для локальной разработки.

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

Локальный запуск без Docker по умолчанию использует `sqlite:///./helpflow.db`. Чтобы подключиться к PostgreSQL вручную, задайте `DATABASE_URL=postgresql+psycopg://user:password@host:5432/database` перед запуском Alembic и API.

## Основной API

```text
POST /api/conversations
GET  /api/conversations/{id}
POST /api/conversations/{id}/messages
POST /api/conversations/{id}/step-result
POST /api/conversations/{id}/escalate
POST /api/conversations/{id}/rating
GET  /api/operator/tickets?scope=queue|mine|resolved
GET  /api/operator/tickets/{id}
POST /api/operator/tickets/{id}/assign
POST /api/operator/tickets/{id}/messages
POST /api/operator/tickets/{id}/resolve
GET  /api/admin/metrics?days=7
GET  /api/admin/operators
POST /api/admin/operators/invite
PATCH /api/admin/operators/{id}
```

Полные схемы запросов и ответов всегда доступны в `/docs` и `/openapi.json`.

React-фронтенд запускается отдельно из корня: `cd apps/web && npm run dev`. Откройте <http://localhost:5173/> для сотрудника и <http://localhost:5173/operator> для оператора. Разрешены origin-порты `3000`, `5173` и `5174`; список настраивается переменной `CORS_ORIGINS` в JSON-формате.

## AI и совместимость

Новые обращения используют `services/ai/helpflow_ai`: вопросы, шаги и карточки берутся из `knowledge-base`. Без внешнего ключа рекомендуется локальная Ollama: задайте `AI_PROVIDER=ollama`, `OLLAMA_MODEL=qwen3.5:9b` и `OLLAMA_BASE_URL=http://host.docker.internal:11434` в корневом `.env`. Docker Desktop передаст запросы в Ollama на macOS или Windows. Для запуска API напрямую без Docker используйте `OLLAMA_BASE_URL=http://localhost:11434`.

Проверьте Ollama командой `ollama list`, затем из корня пересоздайте API через `docker compose up -d --build`. Классификация и управление диалогом остаются быстрыми детерминированными правилами. Для подходящего технического запроса Qwen получает только найденные утверждённые фрагменты базы знаний и возвращает строгий JSON; неизвестный источник, низкая уверенность или ошибка модели дают безопасный ответ правил. Для полностью автономного режима без Ollama задайте `AI_PROVIDER=rules`. `AI_PROVIDER=mock` также отключает сетевые запросы и предназначен прежде всего для тестов. OpenAI-совместимый внешний сервис можно включить через `AI_PROVIDER=openai`, `AI_API_KEY`, `AI_BASE_URL` и `AI_MODEL`.

Рекомендуемая конфигурация `.env` для локальной Qwen:

```dotenv
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=qwen3.5:9b
AI_TIMEOUT_SECONDS=90
```

LLM может улучшать понимание, содержательный ответ по базе знаний и резюме, но не может менять выбранный шаг, вопрос или решение об эскалации; при любой ошибке остаётся исходный ответ сценария. Файл `.env` исключён из Git.

Существующие обращения сохраняют прежнюю логику через `workflow_version=legacy`. Новые получают `triage-v1`. HTTP-контракт сохраняет значения `normal` и `cannot_perform`; адаптер переводит их в AI-значения `medium` и `cannot_do`. В ответ добавлена `escalation_card` с причиной передачи, командой, вопросами, шагами и текущим результатом.

В standalone-запуске AI читает настройки из переменных окружения процесса; `.env` автоматически подставляет Docker Compose. Подробности модуля — в [services/ai/README.md](services/ai/README.md). Проверка AI: `pytest services/ai/tests` из корня после `pip install -e services/ai`.

Debug UI (`/debug`) предназначен для локальной отладки. Основной интерфейс — React-приложение с входом по ролям.

Результаты изучения веток команды и точки интеграции — в [docs/integration-status.md](docs/integration-status.md).

## Командная работа

Общий продуктовый план находится в [PROJECT_PLAN.md](PROJECT_PLAN.md). Контракты backend считаются публичным интерфейсом команды; изменения endpoint или схемы ответа согласовываются до merge.
