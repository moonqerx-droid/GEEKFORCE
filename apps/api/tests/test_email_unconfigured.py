"""Without SMTP settings a lost email is reported in the log, never silently dropped."""

import logging

from app.api.routes.auth import get_email_sender
from app.services.email import EmailPayload, UnconfiguredEmailSender


def test_without_smtp_the_log_says_the_email_was_not_sent(monkeypatch, caplog):
    from app.core import config
    monkeypatch.setattr(config.get_settings(), "smtp_username", "")
    sender = get_email_sender()
    assert isinstance(sender, UnconfiguredEmailSender)
    with caplog.at_level(logging.WARNING):
        sender.send(EmailPayload(recipient="a@b.ru", subject="Код подтверждения HelpFlow: 123456",
                                 text="Код: 123456", html="", action_url=""))
    assert "SMTP is not configured" in caplog.text
    assert "123456" not in caplog.text and "a@b.ru" not in caplog.text
