# HelpFlow Peer Help Design

> **Как реализовано (обновлено при слиянии с main).** В main уже есть настоящие учётные записи и
> сессии, поэтому демо-вход без пароля и заголовок `X-Employee-ID` не понадобились: «Помощь
> коллег» работает от имени вошедшего сотрудника (`require_employee`), вместо таблицы `employees`
> используется `users` (+ колонка `helped_count`), миграция — `20261001_0015`. Опубликовать можно
> только своё обращение. Эндпоинты сотрудников: `GET /api/colleagues`,
> `GET|POST /api/colleagues/{id}/messages`; статус своей просьбы —
> `GET /api/conversations/{id}/peer-help`. Экраны: `/employee/peers`, `/employee/colleagues`.
> Демо-просьбы создаёт `python -m app.seed_demo` от имени Елены, Дмитрия и Ольги. Модерация
> не трогает обычные фразы вроде «сбросьте пароль через портал» и «код ошибки 1603».

## Goal

Add a peer-help channel to HelpFlow without replacing the specialist queue. An employee whose troubleshooting steps did not solve the issue, or whose request is waiting for a specialist, can publish a safe summary to a shared feed. Another employee can volunteer, discuss the issue inside the request, and receive credit when their advice resolves it.

The implementation targets a hackathon demo. It uses selectable demo identities instead of production authentication, polls every four seconds, and preserves every existing support flow.

## Scope

The first release includes:

- `/login` with selectable demo employees and no password;
- a “Помощь коллег” feed with two or three seeded polite requests;
- publication of eligible support requests from the employee conversation page;
- one helper per peer-help request;
- a peer chat attached to the original support conversation;
- server-side moderation of secrets and insults;
- specialist visibility into helper state and peer messages;
- resolution through “Помог совет коллеги” with an atomic helper counter increment;
- an optional “Коллеги” directory and one-to-one direct messages after the request-bound flow works.

The release excludes hierarchy, groups, group chats, WebSockets, production registration, passwords, email verification, and role-based authorization.

## Demo identity

`/login` lists seeded employees as cards. Selecting a card stores the employee ID in `localStorage` and opens the employee workspace. The API receives the employee ID through an `X-Employee-ID` header and rejects unknown IDs with `401`.

Seeded identities:

- Анна Смирнова, Отдел продаж;
- Михаил Волков, IT Operations;
- Елена Орлова, Финансы.

This identity mechanism is explicitly demo-only. The operator route remains the existing unprotected local-demo route and must not be described as production authentication.

## Data model

### Employee

- `id`: stable UUID;
- `name`;
- `department`;
- `helped_count`, non-negative integer;
- `is_demo`;
- timestamps.

### PeerHelpRequest

- `id`;
- `conversation_id`, unique;
- `author_id`;
- `helper_id`, nullable;
- `title` copied from the conversation summary;
- `area` copied from the conversation service;
- `status`: `OPEN`, `HELPING`, `RESOLVED`, or `CANCELLED`;
- timestamps.

Only one active peer-help request may exist for a conversation, and only one helper may claim it. The author cannot claim their own request.

### PeerHelpMessage

- `id`;
- `peer_help_request_id`;
- `sender_id`;
- `content`;
- timestamp.

Only the author and selected helper may read or write the attached chat. The operator ticket endpoint exposes the same messages read-only for the specialist view.

### DirectMessage

The optional employee-directory phase stores sender, recipient, content, and timestamp. It uses the same moderation service. Direct chats remain strictly one-to-one.

## Publication rules

The “Спросить коллег” action is available when a conversation:

- is in `TROUBLESHOOTING` and has at least one completed unsuccessful or impossible step; or
- is `ESCALATED` and is waiting for a specialist.

Publication is forbidden when:

- the playbook is `security_incident`;
- the service is information security;
- the known facts or original request contain phishing, account compromise, leaked credentials, or another security indicator;
- the conversation is already resolved;
- an active peer-help request already exists.

The backend is authoritative. Hiding the button in the UI is only a convenience.

Published cards contain the conversation summary and service area. They do not copy the raw original message, known facts, error text, or previous chat history into the public feed.

## Claiming and chat

An employee presses “Помогу” on an open card. The backend atomically changes the request from `OPEN` to `HELPING` and records the helper. Concurrent claims return `409`; the losing client refreshes the feed and sees the chosen helper.

The author and helper then see a chat panel inside the request. Messages are persisted before they appear in subsequent polling responses. Polling runs every four seconds and pauses when the page is hidden.

The original conversation remains in the specialist queue throughout peer assistance. Operator tickets expose:

- `peer_help_status`;
- author and helper summaries;
- the full peer-help message history;
- a visible “Помогает коллега” marker while status is `HELPING`.

Peer messages do not become ordinary assistant/user messages and do not alter the troubleshooting state machine.

## Resolution and credit

Only the request author may press “Помог совет коллеги”. The backend performs one transaction that:

1. verifies `HELPING` status and an assigned helper;
2. changes the peer-help request to `RESOLVED`;
3. changes the support conversation to `RESOLVED`;
4. clears the active troubleshooting step;
5. adds a system-style assistant message explaining that a colleague's advice solved the issue;
6. increments the helper's `helped_count` by one.

The operation is idempotent: repeated resolution does not increment the counter again. Specialist escalation context remains stored for audit and display.

## Moderation

A single backend moderation service validates peer-help and direct messages. It rejects content rather than silently masking it.

Blocked secret classes include:

- passwords introduced by common labels such as `пароль`, `password`, `pwd`;
- verification and one-time codes;
- bearer tokens, API keys, JWT-like strings, and long credential-like tokens;
- private keys and common access-token prefixes.

Blocked abuse includes a deliberately small Russian and English insult list with word-boundary matching. The design avoids broad sentiment classification so ordinary troubleshooting language is not rejected.

The API returns `422` with a stable code and a clear Russian explanation:

- `secret_detected`: “Не отправляйте пароли, коды или токены. Опишите проблему без секретных данных.”
- `abusive_language`: “Сообщение содержит оскорбление. Переформулируйте его нейтрально.”

The rejected text is not persisted or logged.

## API

Employee identity:

- `GET /api/employees`;
- `GET /api/employees/me`.

Peer-help feed:

- `GET /api/peer-help`;
- `POST /api/conversations/{conversation_id}/peer-help`;
- `POST /api/peer-help/{request_id}/claim`;
- `GET /api/peer-help/{request_id}`;
- `POST /api/peer-help/{request_id}/messages`;
- `POST /api/peer-help/{request_id}/resolve`.

Optional direct messages:

- `GET /api/employees/{employee_id}/messages`;
- `POST /api/employees/{employee_id}/messages`.

All mutating endpoints require `X-Employee-ID`. Read access to a request-bound chat is limited to its author and helper. The feed omits chat messages.

## Frontend

The employee application gains:

- `/login` for demo identity selection;
- `/help` for the peer-help feed;
- a header identity summary and logout action;
- conditional “Спросить коллег” action in the conversation;
- peer-help status and chat inside the active conversation;
- “Помог совет коллеги” for the author;
- “Помог коллегам: N” on employee cards and helper identity;
- optional `/colleagues` directory and direct chat.

Existing conversation restoration remains keyed by the browser, but the stored conversation owner must match the selected demo employee before peer actions are allowed.

The operator UI retains its existing ticket list and adds the helper marker and peer transcript to ticket details.

## Seed data

The migration or application startup creates the three demo employees idempotently. A dedicated seed function creates two or three polite peer-help examples only when the feed is empty. Seeded examples must not reference security incidents or contain sensitive information.

Suggested feed examples:

- “VPN подключается, но корпоративный портал не открывается” — area `VPN`;
- “После обновления Outlook перестал показывать новые письма” — area `Почта`;
- “В браузере CRM постоянно возвращает на страницу входа” — area `CRM`.

Seed data is marked as demo data and can be recreated safely for presentations.

## Compatibility and failure handling

- Existing conversation endpoints keep their response fields and behavior.
- New response fields are optional with safe defaults.
- Peer-help failures never roll back or corrupt the underlying support dialogue.
- Polling errors show a retryable notice and retain typed text.
- Claim conflicts refresh the current request instead of retrying automatically.
- A deleted or unknown demo identity returns the user to `/login`.
- Security incidents remain available to specialists but never enter the employee feed.

## Testing

Backend tests cover:

- publication eligibility and security exclusions;
- feed privacy;
- claim races and self-claim rejection;
- participant-only chat access;
- secret and insult moderation without persistence;
- atomic, idempotent resolution and helper credit;
- unchanged specialist queue membership;
- operator transcript visibility;
- idempotent demo seeding.

Frontend tests cover:

- identity selection and logout;
- publication-button eligibility;
- feed loading and claiming;
- chat polling and moderation errors;
- author-only resolution;
- helper counter rendering;
- specialist helper marker and transcript;
- regression of existing employee and operator flows.

## Demo success criteria

Using two browser profiles, the presenter can select Анна and Михаил, publish Anna's eligible request, claim it as Mikhail, exchange moderated messages, resolve it as Anna, see Mikhail's counter increase, and confirm that the specialist queue retained the ticket and transcript throughout the flow.
