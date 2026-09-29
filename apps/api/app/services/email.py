from dataclasses import dataclass
from email.message import EmailMessage
import logging
import smtplib
from typing import Protocol


@dataclass(frozen=True)
class EmailPayload:
    recipient: str
    subject: str
    text: str
    html: str
    action_url: str


class EmailSender(Protocol):
    def send(self, message: EmailPayload) -> None: ...


class MemoryEmailSender:
    def __init__(self):
        self.messages: list[EmailPayload] = []

    def send(self, message: EmailPayload) -> None:
        self.messages.append(message)


logger = logging.getLogger(__name__)


class UnconfiguredEmailSender(MemoryEmailSender):
    """No SMTP settings: nothing can be sent, so say so in the log instead of failing silently."""

    def send(self, message: EmailPayload) -> None:
        super().send(message)
        # Neither the code nor the address is logged: logs are read by more people than the mailbox.
        logger.warning("email.not_sent: SMTP is not configured — set SMTP_USERNAME, "
                       "SMTP_PASSWORD and SMTP_FROM_EMAIL in .env")


class SmtpEmailSender:
    def __init__(self, *, host: str, port: int, username: str, password: str,
                 from_email: str, from_name: str = "HelpFlow", security: str = "ssl"):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.from_email = from_email
        self.from_name = from_name
        self.security = security

    def send(self, message: EmailPayload) -> None:
        email = EmailMessage()
        email["Subject"] = message.subject
        email["From"] = f"{self.from_name} <{self.from_email}>"
        email["To"] = message.recipient
        email.set_content(message.text)
        email.add_alternative(message.html, subtype="html")
        if self.security == "ssl":
            with smtplib.SMTP_SSL(self.host, self.port, timeout=10) as smtp:
                smtp.login(self.username, self.password)
                smtp.send_message(email)
        else:
            with smtplib.SMTP(self.host, self.port, timeout=10) as smtp:
                smtp.starttls()
                smtp.login(self.username, self.password)
                smtp.send_message(email)
