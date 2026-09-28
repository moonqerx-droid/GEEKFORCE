"""Text on screenshots: the error an employee attached instead of retyping it.

Tesseract (installed in the API image, Russian + English) reads the picture locally,
in about a second. Without the binary or on any failure the result is None and the
dialogue behaves as before: it simply does not know what the picture says.
"""

from __future__ import annotations

import io
import logging
import re

logger = logging.getLogger(__name__)

try:  # optional: the API works without OCR
    import pytesseract
    from PIL import Image, ImageOps
except ImportError:  # pragma: no cover - exercised only without the extras
    pytesseract = None
    Image = ImageOps = None

IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
MAX_CHARS = 400
TIMEOUT_SECONDS = 8
# A line that names a failure: the one worth quoting back and filing as the error text.
_ERROR_HINT = re.compile(
    r"ошибк|error|не удал|не удается|не удаётся|невозможно|failed|denied|запрещ|недоступ|"
    r"неверн|истек|истёк|заблокир|нет подключ|не найден|not found|timeout|0x[0-9a-f]{4,}|\b\d{3,4}\b",
    re.IGNORECASE,
)
# Window chrome and buttons that carry no meaning.
_NOISE = re.compile(r"^(ок|ok|отмена|cancel|да|нет|закрыть|close|файл правка вид.*|справка)$", re.IGNORECASE)


def available() -> bool:
    if pytesseract is None:
        return False
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:  # noqa: BLE001 - binary missing or broken
        return False


def read_text(data: bytes, content_type: str) -> str | None:
    """Meaningful text lines of an image, or None if there is none or OCR is unavailable."""
    if content_type not in IMAGE_TYPES or pytesseract is None:
        return None
    try:
        image = Image.open(io.BytesIO(data))
        image = ImageOps.grayscale(image.convert("RGB"))
        if image.width < 1400:  # small screenshots read far better enlarged
            scale = 2 if image.width >= 700 else 3
            image = image.resize((image.width * scale, image.height * scale))
        raw = pytesseract.image_to_string(image, lang="rus+eng", timeout=TIMEOUT_SECONDS)
    except Exception as error:  # noqa: BLE001 - unreadable picture or no binary
        logger.info("ocr.skipped error=%s", type(error).__name__)
        return None
    return clean(raw)


def clean(raw: str) -> str | None:
    lines = []
    for line in raw.splitlines():
        line = re.sub(r"\s+", " ", line).strip(" |_—-")
        letters = sum(ch.isalpha() for ch in line)
        if letters >= 3 and not _NOISE.match(line) and letters / max(len(line), 1) > 0.5:
            lines.append(line)
    text = "\n".join(dict.fromkeys(lines))
    return text[:MAX_CHARS].strip() or None


def error_line(text: str) -> str | None:
    """The line that names the failure, if the screenshot has one."""
    for line in text.splitlines():
        if _ERROR_HINT.search(line):
            return line[:160]
    return None
