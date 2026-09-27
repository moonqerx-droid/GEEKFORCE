# services/ai — AI triage (участник 3)

Модуль понимает обращение, выбирает сценарий из базы знаний, задаёт уточняющие
вопросы, выдаёт шаги по одному и готовит карточку эскалации.

**Принцип:** LLM улучшает понимание текста, пишет резюме и может сделать уже выбранный
ответ более естественным. Какой вопрос задать, какой шаг показать и когда эскалировать,
всегда решает детерминированный код. Рендерер получает только подготовленный ответ и
тип действия — история и собранные факты повторно ему не отправляются. Поэтому
упавший, медленный или «галлюцинирующий» LLM не ломает диалог. Без ключа всё работает
на правилах (`AI_PROVIDER=mock`, это значение по умолчанию).

Для `AI_PROVIDER=ollama` классификация и обычные вопросы/шаги остаются на быстрых
локальных правилах. Локальная 9B-модель не вызывается ради косметического
перефразирования или резюме в синхронном пути сообщения. Резюме эскалации собирается
из фактов и результатов шагов по шаблону. Выборочные RAG-вызовы ещё не реализованы.
Внешний `openai`-режим может дополнительно улучшать
классификацию и формулировки.

## Быстрый старт

```bash
cd services/ai
pip install -e ".[dev]"
pytest -q                 # 133 теста, без сети
python -m helpflow_ai     # интерактивное демо в консоли
```

## Настройки (env)

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `AI_PROVIDER` | `mock` | `mock` — правила; `ollama` — локальная модель без ключа; `openai` — внешний OpenAI-совместимый API |
| `AI_API_KEY` | — | нужен для `openai`; для `ollama` не требуется |
| `AI_BASE_URL` | `https://api.openai.com/v1` | можно указать OpenRouter, YandexGPT-прокси, локальный vLLM/Ollama |
| `AI_MODEL` | `gpt-4o-mini` | имя модели |
| `AI_TIMEOUT_SECONDS` | `15` | таймаут запроса; при ошибке 1 повтор, затем fallback на правила |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | нативный endpoint Ollama; в Docker используйте `http://host.docker.internal:11434` |
| `OLLAMA_MODEL` | `qwen3.5:9b` | имя установленной локальной модели |
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
# decision.message_source: "rules" или "llm"; остальные поля всегда выбраны правилами
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
`current_result` (текущий результат), `escalation_reason`, `recommended_team`, `ai_summary`, `source` (`llm` или `rules`),
`issues` (все проблемы из обращения со статусами, см. ниже).

## Изменения контракта

Все изменения добавочные: новые поля опциональные, у них есть значения по умолчанию.
Старые поля и методы не переименованы. Backend может ничего не менять, диалог работает и так.

| Где | Поле | Что это |
|---|---|---|
| `Analysis` | `additional_issues: list[DetectedIssue]` | остальные проблемы из того же сообщения в порядке разбора. Главная проблема по-прежнему в `recommended_playbook`/`service`/`symptoms` |
| `Decision` | `playbook_id: str \| None` | к какой проблеме относится этот ход. Отличается от `conversation.playbook_id`, когда разбираем вторую или третью проблему |
| `EscalationCard` | `issues: list[DetectedIssue]` | все проблемы обращения, первая главная; у каждой `status` |
| `Step` | `workaround: bool` | быстрый обходной путь (телефон, веб-версия, раздача интернета). Результат `helped` не закрывает проблему, диагностика продолжается |
| `Question`, `Step`, `Playbook` | `when_symptoms`, `unless_symptoms`, `only_without_symptoms`, `escalate_on_symptoms`, `escalation_note` | поля YAML-сценариев, см. «База знаний» |

`DetectedIssue`: `playbook_id`, `title`, `service`, `symptoms`, `evidence` (фрагмент текста
пользователя, как он написан), `status`: `pending` (ещё не разбирали), `in_progress` (в работе),
`resolved` (шаг помог или пользователь сказал, что проблема ушла).

**Несколько проблем без нового состояния.** План разбора движок каждый раз заново строит из
`original_request`, поэтому backend хранит только то, что хранил раньше. Порядок: сначала
корневая причина (сеть, затем VPN), при срочности следом звонок, дальше в порядке текста.
Когда шаг по одной проблеме помог, `decide()` вместо `verify` возвращает `ask` с фактом
`issue_resolved.<playbook_id>` («Теперь следующая проблема — … Сейчас с этим всё в порядке?»).
Backend обрабатывает его как обычный уточняющий вопрос: `asked_facts`, затем `absorb_answer`.
`verify` приходит, только когда решены все проблемы.

**Что стоит сделать в backend** (не обязательно):
- при `escalate` показывать `decision.message`. Сейчас `_escalate` пишет свой текст, и
  пояснение движка теряется («новый доступ выдают администраторы…», «готового решения нет…»);
- показывать `escalation_card.issues` оператору списком со статусами;
- `conversation.missing_facts` в `_advance` лучше брать из `Analysis`, а не из всех вопросов
  сценария: часть вопросов теперь зависит от симптома.

## Для Incident Radar (участник 4)

`Analysis.service`, `Analysis.symptoms` и `known_facts.error_text` (например, `ошибка 502`)
годятся как признаки для кластеризации. Сценарий `mass_incident` срабатывает на фразы
вроде «у коллег тоже», «у всех», «весь отдел»: сразу `urgency=critical` и `should_escalate=true`.

## База знаний

`knowledge-base/playbooks/*.yaml`: 12 сценариев (CRM, пароль, VPN, почта, сеть/Wi-Fi,
видеозвонки, права доступа, принтер, недоступность сервиса, массовый сбой, ИБ, неизвестная проблема).
Формат шага: `when` / `unless` задают условия по фактам, поэтому ответ на вопрос меняет
следующий шаг. Опечатка в YAML сразу валит загрузку (Pydantic `extra=forbid`).

Условия по симптомам (симптомы ищутся по `symptoms_hints` во всём, что написал пользователь):
- `when_symptoms` / `unless_symptoms` у вопроса и шага: задавать или показывать только при этих
  симптомах или только без них. Так «Teams не запускается» не получает вопрос про гарнитуру;
- `only_without_symptoms: true` у вопроса: спросить «что именно не так?», только если симптом неизвестен;
- `workaround: true` у шага: при срочности `high`/`critical` этот шаг идёт первым, до вопросов;
- `escalate_on_symptoms` у сценария: после вопросов сразу передать специалисту. Например, новый
  доступ пользователь сам не получит. `escalation_note` добавляется к сообщению, в нём можно
  подставлять факты: `{resource}`.

Если сценария нет, но пользователь назвал устройство или программу («мышка», «монитор»,
«Excel»), движок не задаёт вопрос «какая программа не работает?», а сразу честно передаёт
обращение специалисту. Факт `service_name` и `Analysis.service` при этом заполнены.

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
