import re


class ModerationViolation(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


SECRET_MESSAGE = "Не отправляйте пароли, коды или токены. Опишите проблему без секретных данных."
ABUSE_MESSAGE = "Сообщение содержит оскорбление. Переформулируйте его нейтрально."

SECRET_PATTERNS = (
    # «пароль: …», «пароль — …» или «пароль Qwerty123»; «сбросьте пароль через портал» — не секрет.
    re.compile(r"\b(?:парол(?:ь|я|ем)?|password|passwd|pwd)\b(?:\s*[:=—–-]\s*\S+|\s+(?=\S*\d)\S{6,})", re.I),
    # «код из смс 4829», но не «код ошибки 1603».
    re.compile(r"\b(?:код|otp|one[- ]time code)\b(?!\s+ошибк)[^\d\n]{0,24}?\b\d{4,8}\b", re.I),
    re.compile(r"\bbearer\s+[a-z0-9._~+/=-]{12,}", re.I),
    re.compile(r"\beyJ[a-zA-Z0-9_-]{8,}\.[a-zA-Z0-9_-]{8,}\.[a-zA-Z0-9_-]{6,}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.I),
    re.compile(r"\b(?:api[_ -]?key|access[_ -]?token|secret)\b\s*[:=]\s*[a-z0-9_-]{12,}", re.I),
    re.compile(r"\b(?:sk|ghp|glpat)-[a-z0-9_-]{12,}\b", re.I),
)
ABUSE_PATTERN = re.compile(r"\b(?:идиот|дебил|тупиц[аы]|moron|idiot)\b", re.I)


def validate_peer_message(content: str) -> str:
    cleaned = content.strip()
    if not cleaned:
        raise ValueError("message must not be blank")
    if any(pattern.search(cleaned) for pattern in SECRET_PATTERNS):
        raise ModerationViolation("secret_detected", SECRET_MESSAGE)
    if ABUSE_PATTERN.search(cleaned):
        raise ModerationViolation("abusive_language", ABUSE_MESSAGE)
    return cleaned
