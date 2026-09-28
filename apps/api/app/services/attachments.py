"""Accepting, checking and handing out files attached to conversations."""

from __future__ import annotations

import hashlib
import unicodedata
from pathlib import PurePath

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.attachment import Attachment
from app.models.auth import User
from app.models.conversation import Conversation

MAX_BYTES = 10 * 1024 * 1024
MAX_PER_MESSAGE = 5

# Extension → content type we will serve. Anything else is refused: no SVG/HTML
# (script in an image), no executables, no archives that hide what is inside.
ALLOWED = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".heic": "image/heic",
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".log": "text/plain",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


class AttachmentRejected(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _looks_like(content_type: str, data: bytes) -> bool:
    """The bytes must match the declared type, so a renamed file cannot slip through."""
    head = data[:16]
    if content_type == "image/png":
        return head.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/jpeg":
        return head.startswith(b"\xff\xd8\xff")
    if content_type == "image/gif":
        return head.startswith((b"GIF87a", b"GIF89a"))
    if content_type == "image/webp":
        return head.startswith(b"RIFF") and data[8:12] == b"WEBP"
    if content_type == "image/heic":
        return data[4:8] == b"ftyp"
    if content_type == "application/pdf":
        return head.startswith(b"%PDF-")
    if content_type.startswith("application/vnd.openxmlformats"):
        return head.startswith(b"PK\x03\x04")
    if content_type == "text/plain":
        try:
            data[:4096].decode("utf-8")
        except UnicodeDecodeError:
            return False
        return b"\x00" not in data[:4096]
    return False


def clean_filename(raw: str | None) -> str:
    name = PurePath((raw or "file").replace("\\", "/")).name
    name = unicodedata.normalize("NFC", "".join(ch for ch in name if ch.isprintable())).strip()
    return (name or "file")[:200]


class AttachmentService:
    def __init__(self, session: Session):
        self.session = session

    def store(self, conversation: Conversation, uploader: User, filename: str | None, data: bytes) -> Attachment:
        if len(data) > MAX_BYTES:
            raise AttachmentRejected(413, "Файл больше 10 МБ")
        if not data:
            raise AttachmentRejected(415, "Файл пустой")
        name = clean_filename(filename)
        content_type = ALLOWED.get(PurePath(name).suffix.lower())
        if content_type is None or not _looks_like(content_type, data):
            raise AttachmentRejected(415, "Такой файл прикрепить нельзя: подойдут фото, скриншоты, PDF, TXT, LOG, DOCX и XLSX")
        attachment = Attachment(
            conversation_id=conversation.id,
            uploader_id=uploader.id,
            filename=name,
            content_type=content_type,
            size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            data=data,
        )
        self.session.add(attachment)
        self.session.commit()
        return attachment

    def pending_for(self, conversation_id: str, ids: list[str]) -> list[Attachment]:
        """Files uploaded to this conversation and not yet part of any message."""
        if not ids:
            return []
        if len(set(ids)) != len(ids):
            raise AttachmentRejected(409, "Один и тот же файл прикреплён дважды")
        found = self.session.scalars(select(Attachment).where(Attachment.id.in_(ids))).all()
        by_id = {item.id: item for item in found}
        ordered = [by_id.get(item_id) for item_id in ids]
        if any(item is None or item.conversation_id != conversation_id or item.message_id is not None for item in ordered):
            raise AttachmentRejected(409, "Файл не найден в этом обращении или уже отправлен")
        return ordered  # type: ignore[return-value]

    def get_for(self, attachment_id: str, viewer: User) -> Attachment | None:
        attachment = self.session.get(Attachment, attachment_id)
        if attachment is None:
            return None
        conversation = self.session.get(Conversation, attachment.conversation_id)
        if conversation is None:
            return None
        if conversation.owner_id == viewer.id:
            return attachment
        # Support sees files only once the conversation was handed to people.
        handed_off = conversation.escalated_at is not None or conversation.status in {"ESCALATED", "IN_PROGRESS"}
        if viewer.role in {"operator", "admin"} and handed_off:
            return attachment
        return None
