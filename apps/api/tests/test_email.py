from email.message import EmailMessage

from app.services.email import EmailPayload, MemoryEmailSender


def test_memory_sender_records_complete_message():
    sender = MemoryEmailSender()
    payload = EmailPayload(
        recipient="anna@example.ru",
        subject="Подтвердите email",
        text="Откройте ссылку",
        html="<p>Откройте ссылку</p>",
        action_url="http://localhost/verify?token=secret",
    )
    sender.send(payload)
    assert sender.messages == [payload]
