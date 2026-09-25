# services/ai — AI triage (участник 3)

Модуль понимает обращение, выбирает сценарий из базы знаний, задаёт уточняющие
вопросы, выдаёт шаги по одному и готовит карточку эскалации.

**Принцип:** LLM только улучшает понимание текста и пишет резюме. Какой вопрос задать,
какой шаг показать и когда эскалировать, всегда решает детерминированный код. Поэтому
упавший, медленный или «галлюцинирующий» LLM не ломает диалог. Без ключа всё работает
на правилах (`AI_PROVIDER=mock`, это значение по умолчанию).

## Быстрый старт

```bash
cd services/ai
pip install -e ".[dev]"
pytest -q                 # 35 тестов, без сети
python -m helpflow_ai     # интерактивное демо в консоли
```

## Настройки (env)

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `AI_PROVIDER` | `mock` | `mock` — только правила; `openai` — любой OpenAI-совместимый API |
| `AI_API_KEY` | — | ключ; без него LLM отключается |
| `AI_BASE_URL` | `https://api.openai.com/v1` | можно указать OpenRouter, YandexGPT-прокси, локальный vLLM/Ollama |
| `AI_MODEL` | `gpt-4o-mini` | имя модели |
| `AI_TIMEOUT_SECONDS` | `15` | таймаут запроса; при ошибке 1 повтор, затем fallback на правила |
| `HELPFLOW_KB_DIR` | `<repo>/knowledge-base` | путь к базе знаний (нужен в Docker) |

## Интеграция с backend (apps/api)

```python
from helpflow_ai import TriageEngine, ConversationContext, StepRecord, DecisionAction

engine = TriageEngine.from_env()          # один экземпляр на приложение

# 1. Первое сообщение: ANALYZING
analysis = engine.analyze(text)           # -> Analysis (JSON из раздела 7 PROJECT_PLAN)
# сохранить в Conversation: summary, service, symptoms, urgency, urgency_reason,
# known_facts, missing_facts, confidence, playbook_id = analysis.recommended_playbook

# 2. Что делать дальше: вызывать после каждого события
ctx = ConversationContext(
    original_request=conv.messages[0].content,
    messages=[{"role": m.role, "content": m.content} for m in conv.messages],
    known_facts=conv.known_facts,
    asked_facts=conv.asked_facts,          # новое поле: факты, о которых уже спросили
    completed_steps=[StepRecord(step_id=s.code, outcome=s.outcome) for s in conv.completed_steps],
    playbook_id=conv.playbook_id,
    urgency=conv.urgency,
    verification_failed=conv.verification_failed,
)
decision = engine.decide(ctx)             # -> Decision
```

| `decision.action` | Статус диалога | Что сделать backend |
|---|---|---|
| `ask` | `CLARIFYING` | показать `decision.message`; добавить `decision.question.fact` в `asked_facts` |
| `step` | `TROUBLESHOOTING` | показать `decision.message`, сохранить `decision.step.id` как текущий шаг |
| `verify` | `VERIFYING` | показать `decision.message` (вопрос «проблема решена?») |
| `escalate` | `ESCALATED` | `engine.build_escalation_card(ctx, decision.reason)` → карточка для оператора |

Ответ пользователя на уточняющий вопрос:

```python
new_facts = engine.absorb_answer(text, ctx)   # {"vpn": "no", ...}
conv.known_facts.update(new_facts)
```

Ответ на проверку результата (состояние `VERIFYING`):

```python
solved = engine.interpret_confirmation(text)  # True / False / None (непонятно, переспросить)
# True  -> RESOLVED
# False -> verification_failed = True, снова decide() (следующий шаг или эскалация)
# после каждого нового step-result сбрасывать verification_failed = False
```

`StepOutcome` совпадает с API: `helped`, `not_helped`, `cannot_do`.

### Карточка эскалации (`EscalationCard`)

`original_request`, `summary`, `service`, `urgency`, `urgency_reason`, `known_facts`,
`questions_and_answers[{question, answer}]`, `performed_steps[{step_id, step, result}]`,
`escalation_reason`, `recommended_team`, `ai_summary`, `source` (`llm` или `rules`).

## Для Incident Radar (участник 4)

`Analysis.service`, `Analysis.symptoms` и `known_facts.error_text` (например, `ошибка 502`)
годятся как признаки для кластеризации. Сценарий `mass_incident` срабатывает на фразы
вроде «у коллег тоже», «у всех», «весь отдел»: сразу `urgency=critical` и `should_escalate=true`.

## База знаний

`knowledge-base/playbooks/*.yaml`: 11 сценариев (CRM, пароль, VPN, почта, сеть/Wi-Fi,
видеозвонки, права доступа, недоступность сервиса, массовый сбой, ИБ, неизвестная проблема).
Формат шага: `when` / `unless` задают условия по фактам, поэтому ответ на вопрос меняет
следующий шаг. Опечатка в YAML сразу валит загрузку (Pydantic `extra=forbid`).

`knowledge-base/test-cases/triage_cases.yaml`: контрольные обращения. Добавили кейс,
запустили `pytest`, и он проверяется автоматически.

## Структура

```text
helpflow_ai/
├── schemas.py    # Pydantic-контракты
├── knowledge.py  # загрузка playbook-ов
├── rules.py      # классификация, срочность, факты, разбор ответов (fallback без LLM)
├── llm.py        # OpenAI-совместимый клиент: JSON-режим, повтор, таймаут
├── prompts.py    # промпты (текст пользователя изолирован от инструкций)
├── engine.py     # TriageEngine — публичный вход
└── __main__.py   # консольное демо
```
