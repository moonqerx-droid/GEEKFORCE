import pytest

from app.services.moderation import ModerationViolation, validate_peer_message


@pytest.mark.parametrize("text", [
    "мой пароль: qwerty123", "код из смс 482911", "Bearer abcdefghijklmnop",
    "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.signature",
    "-----BEGIN PRIVATE KEY-----", "api_key=sk-test-1234567890123456",
])
def test_secrets_are_rejected(text):
    with pytest.raises(ModerationViolation) as error:
        validate_peer_message(text)
    assert error.value.code == "secret_detected"


def test_insult_is_rejected():
    with pytest.raises(ModerationViolation) as error:
        validate_peer_message("Ты идиот")
    assert error.value.code == "abusive_language"


def test_safe_technical_message_is_returned_stripped():
    assert validate_peer_message("  Попробуйте перезапустить VPN-клиент.  ") == "Попробуйте перезапустить VPN-клиент."


@pytest.mark.parametrize("text", [
    "Сбросьте пароль через портал самообслуживания",
    "Забыл пароль и не могу войти",
    "У меня код ошибки 1603 при установке",
    "Ошибка 809, код ошибки 0x80070005",
    "Смените пароль, и VPN заработает",
])
def test_ordinary_support_talk_passes(text):
    assert validate_peer_message(text) == text


@pytest.mark.parametrize("text", ["пароль Qwerty123", "пароль — Zima2026!", "код подтверждения 4829"])
def test_secret_values_without_colon_are_rejected(text):
    with pytest.raises(ModerationViolation):
        validate_peer_message(text)
