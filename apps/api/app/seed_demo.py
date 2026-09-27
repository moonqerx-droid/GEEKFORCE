"""Fill the database with demo accounts and two weeks of realistic support history.

Run from apps/api:  python -m app.seed_demo
Idempotent: if the demo admin already exists, nothing is changed.
Every conversation is played through the real rules engine, so escalation cards,
questions and steps look exactly like production ones.
"""

from __future__ import annotations

import random
from datetime import timedelta

from helpflow_ai import TriageEngine
from helpflow_ai.knowledge import KnowledgeBase
from sqlalchemy import select

from app.core.security import hash_password, utc_now
from app.db.session import SessionLocal
from app.models.auth import User
from app.models.conversation import Conversation
from app.repositories.conversations import ConversationRepository
from app.services.admin import _aware
from app.services.operator import OperatorService
from app.services.triage import TriageDialogueService

PASSWORD = "DemoPass123"
DOMAIN = "helpflow.demo"

STAFF = [
    ("admin", "Мария", "Иванова", "admin"),
    ("anna", "Анна", "Смирнова", "operator"),
    ("oleg", "Олег", "Кузнецов", "operator"),
]
EMPLOYEES = [
    ("ivan", "Иван", "Петров", "sales"),
    ("elena", "Елена", "Соколова", "marketing"),
    ("dmitry", "Дмитрий", "Волков", "finance"),
    ("olga", "Ольга", "Морозова", "hr"),
    ("sergey", "Сергей", "Новиков", "operations"),
]

# (first message, weight). Mixed tone on purpose: emotional, vague, urgent, calm.
REQUESTS = [
    ("Не подключается VPN из дома, пишет ошибку подключения", 6),
    ("VPN постоянно отваливается каждые 10 минут, невозможно работать", 3),
    ("Outlook не получает новые письма со вчерашнего дня", 5),
    ("Забыл пароль, не могу войти в компьютер", 5),
    ("Учётная запись заблокирована после смены пароля", 3),
    ("Не могу зайти в CRM с ноутбука, с телефона открывается, через 20 минут встреча", 4),
    ("В Zoom собеседники меня не слышат", 4),
    ("Wi-Fi в офисе очень медленный, страницы грузятся по минуте", 3),
    ("Нужен доступ к папке отдела на общем диске", 4),
    ("Не открывается корпоративный портал, пишет 502", 2),
    ("Пришло странное письмо от «бухгалтерии» с архивом, я его открыл", 1),
    ("У всего отдела не работает интернет", 1),
    ("Всё сломалось, ничего не работает, помогите", 2),
]

OPERATOR_REPLIES = [
    "Здравствуйте! Посмотрела ваше обращение, контекст весь есть — сейчас проверю на своей стороне.",
    "Добрый день! Вижу, какие шаги вы уже сделали, повторять их не нужно. Проверяю учётную запись.",
    "Здравствуйте! Нашёл причину: на сервере зависла ваша сессия. Сбросил её — попробуйте ещё раз.",
]
EMPLOYEE_FOLLOWUPS = ["Спасибо, жду", "Попробовал — теперь всё работает!", "Да, заработало, спасибо"]
RESOLUTIONS = [
    "Сброшена зависшая сессия, вход восстановлен",
    "Выдан доступ к ресурсу по согласованию с руководителем",
    "Переустановлен профиль почты, синхронизация восстановлена",
    "Обновлены сертификаты VPN-клиента",
]


def _user(session, key, first, last, role, department="it"):
    user = User(
        first_name=first, last_name=last, email=f"{key}@{DOMAIN}", department=department,
        password_hash=hash_password(PASSWORD), role=role, email_verified_at=utc_now(),
    )
    session.add(user)
    return user


def _play(service: TriageDialogueService, conversation_id: str, text: str, *, solve: bool, rng: random.Random):
    """Walk one conversation through the real engine until it resolves or escalates."""
    current = service.handle_message(conversation_id, text)
    for _ in range(12):
        if current.status in {"RESOLVED", "ESCALATED"}:
            return current
        if current.status == "CLARIFYING":
            current = service.handle_message(conversation_id, rng.choice(["Да", "Нет", "Ошибка подключения"]))
        elif current.status == "TROUBLESHOOTING":
            outcome = "helped" if solve and rng.random() < 0.75 else "not_helped"
            current = service.record_step_result(conversation_id, outcome)
        elif current.status == "VERIFYING":
            current = service.handle_message(conversation_id, "Да, всё работает, спасибо" if solve else "Нет, не работает")
    if current.status not in {"RESOLVED", "ESCALATED"}:
        current = service.escalate(conversation_id)
    return current


def _shift(conversation: Conversation, start) -> None:
    """Move the whole conversation back in time, keeping a believable pace."""
    offset = start - _aware(conversation.created_at)
    conversation.created_at = start
    for index, message in enumerate(conversation.messages):
        message.created_at = start + timedelta(seconds=40 * index)
    for index, step in enumerate(conversation.steps):
        step.created_at = start + timedelta(minutes=1 + 2 * index)
    for field in ("escalated_at", "assigned_at", "first_operator_reply_at", "resolved_at"):
        value = getattr(conversation, field)
        if value is not None:
            setattr(conversation, field, _aware(value) + offset)
    conversation.updated_at = conversation.resolved_at or conversation.created_at


def seed(total: int = 60, seed_value: int = 42) -> bool:
    rng = random.Random(seed_value)
    with SessionLocal() as session:
        if session.scalar(select(User).where(User.email == f"admin@{DOMAIN}")):
            return False
        staff = {key: _user(session, key, first, last, role) for key, first, last, role in STAFF}
        employees = [_user(session, key, first, last, "employee", dept) for key, first, last, dept in EMPLOYEES]
        session.commit()
        operators = [staff["anna"], staff["oleg"]]

        engine = TriageEngine(KnowledgeBase.load(), None)
        repository = ConversationRepository(session)
        dialogue = TriageDialogueService(repository, engine)
        specialist = OperatorService(session)
        texts = [text for text, weight in REQUESTS for _ in range(weight)]
        now = utc_now()

        for index in range(total):
            fresh = index >= total - 5  # the last few stay open in the queue for the live demo
            text = rng.choice(texts)
            conversation = dialogue.create_conversation()
            conversation.owner_id = rng.choice(employees).id
            session.commit()
            result = _play(dialogue, conversation.id, text, solve=not fresh and rng.random() < 0.85, rng=rng)

            if result.status == "ESCALATED" and not fresh:
                operator = rng.choice(operators)
                specialist.assign(result.id, operator)
                specialist.reply(result.id, operator, rng.choice(OPERATOR_REPLIES))
                dialogue.handle_message(result.id, rng.choice(EMPLOYEE_FOLLOWUPS))
                specialist.resolve(result.id, operator, rng.choice(RESOLUTIONS))
            elif result.status == "ESCALATED" and index == total - 1:
                specialist.assign(result.id, operators[1])
                specialist.reply(result.id, operators[1], OPERATOR_REPLIES[1])

            conversation = repository.get(result.id)
            if fresh:
                start = now - timedelta(minutes=rng.randint(3, 40))
            else:
                start = now - timedelta(days=rng.randint(0, 13), hours=rng.randint(0, 9), minutes=rng.randint(0, 59))
            _shift(conversation, start)
            if conversation.resolved_by == "operator":
                assigned = conversation.escalated_at + timedelta(minutes=rng.randint(2, 15))
                reply = assigned + timedelta(minutes=rng.randint(1, 6))
                conversation.assigned_at, conversation.first_operator_reply_at = assigned, reply
                conversation.resolved_at = reply + timedelta(minutes=rng.randint(8, 70))
            elif conversation.resolved_by == "assistant":
                conversation.resolved_at = start + timedelta(minutes=rng.randint(3, 14))
            if conversation.status == "RESOLVED" and rng.random() < 0.6:
                conversation.rating = rng.choices([5, 4, 3, 2], weights=[55, 30, 10, 5])[0]
            session.commit()
        return True


def main() -> None:
    created = seed()
    if not created:
        print(f"Демо-данные уже есть. Вход: admin@{DOMAIN} / {PASSWORD}")
        return
    print("Демо-данные созданы. Пароль всех аккаунтов:", PASSWORD)
    print(f"  Админ:     admin@{DOMAIN}")
    print(f"  Операторы: anna@{DOMAIN}, oleg@{DOMAIN}")
    print(f"  Сотрудники: {', '.join(f'{key}@{DOMAIN}' for key, *_ in EMPLOYEES)}")


if __name__ == "__main__":
    main()
