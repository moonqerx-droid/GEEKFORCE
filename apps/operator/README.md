# apps/operator

Операторская панель GEEKFORCE HelpFlow.

Владелец: Участник 4.

## Назначение

Интерфейс специалиста поддержки:

- очередь эскалированных обращений, отсортированная по срочности;
- полная карточка эскалации со всем контекстом;
- экран массового инцидента (Incident Radar);
- рассылка статуса связанным пользователям.

## Статус

Заглушка. Стек фиксируется командой. Текущий `index.html` — временная точка входа.

## План

См. [docs/operator-panel-plan.md](../../docs/operator-panel-plan.md).

## Эндпоинты

```

GET  /api/operator/tickets
GET  /api/operator/incidents
POST /api/operator/incidents/{id}/broadcast

```

