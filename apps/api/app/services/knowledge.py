"""Admin knowledge base: validate an upload, extract its text, chunk it, keep an audit trail.

The request is refused (HTTP 4xx, nothing stored) when the upload itself is wrong: unknown
extension, declared type that does not fit it, empty or oversized body, checksum mismatch or
a duplicate. When the file is fine as an upload but its content cannot become knowledge
(spoofed, corrupt, encrypted, no text), the document is kept as `failed` with a reason the
admin can read. The original bytes are never written to disk.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import utc_now
from app.models.audit import AdminAuditEvent
from app.models.auth import User
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.repositories.knowledge import KnowledgeRepository
from app.services.chunking import chunk_text
from app.services.document_extraction import (
    ExtractionError,
    declared_type_matches,
    extract_document,
    file_format,
    media_type_for,
    safe_filename,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class KnowledgeLimits:
    max_upload_bytes: int = 10 * 1024 * 1024
    max_extracted_chars: int = 500_000
    max_pdf_pages: int = 200
    chunk_chars: int = 1200
    chunk_overlap: int = 150

    @classmethod
    def from_settings(cls, settings: Settings) -> "KnowledgeLimits":
        return cls(
            max_upload_bytes=settings.knowledge_max_upload_bytes,
            max_extracted_chars=settings.knowledge_max_extracted_chars,
            max_pdf_pages=settings.knowledge_max_pdf_pages,
            chunk_chars=settings.knowledge_chunk_chars,
            chunk_overlap=settings.knowledge_chunk_overlap,
        )


class KnowledgeUploadRefused(Exception):
    def __init__(self, status_code: int, message: str, document_id: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.document_id = document_id


class KnowledgeDocumentNotFound(LookupError):
    pass


class KnowledgeService:
    def __init__(self, session: Session, limits: KnowledgeLimits | None = None):
        self.session = session
        self.limits = limits or KnowledgeLimits()
        self.repository = KnowledgeRepository(session)

    # --- reading ------------------------------------------------------------------

    def list_documents(self) -> list[KnowledgeDocument]:
        return self.repository.list_documents()

    def get(self, document_id: str) -> KnowledgeDocument:
        document = self.repository.get(document_id)
        if document is None:
            raise KnowledgeDocumentNotFound(document_id)
        return document

    # --- writing ------------------------------------------------------------------

    def upload(
        self,
        filename: str,
        content: bytes,
        declared_type: str | None,
        actor: User,
        *,
        title: str | None = None,
        service: str | None = None,
        checksum: str | None = None,
    ) -> KnowledgeDocument:
        name = safe_filename(filename)
        fmt = file_format(name)
        if fmt is None:
            raise KnowledgeUploadRefused(415, "Поддерживаются только PDF, DOCX, TXT и MD.")
        if not declared_type_matches(fmt, declared_type):
            raise KnowledgeUploadRefused(415, "Тип файла не соответствует расширению.")
        if not content:
            raise KnowledgeUploadRefused(422, "Файл пустой.")
        if len(content) > self.limits.max_upload_bytes:
            megabytes = self.limits.max_upload_bytes / (1024 * 1024)
            raise KnowledgeUploadRefused(413, f"Файл больше {megabytes:g} МБ.")
        digest = hashlib.sha256(content).hexdigest()
        if checksum and checksum.strip().lower() != digest:
            raise KnowledgeUploadRefused(422, "SHA-256 не совпадает: файл повреждён при передаче.")
        duplicate = self.repository.find_active_duplicate(digest)
        if duplicate is not None:
            raise KnowledgeUploadRefused(409, "Такой документ уже загружен.", duplicate.id)

        document = KnowledgeDocument(
            title=_clean_label(title, 200) or name.rsplit(".", 1)[0] or name,
            original_filename=name,
            media_type=media_type_for(fmt),
            size_bytes=len(content),
            sha256=digest,
            service=_clean_label(service, 120),
            status="processing",
            uploaded_by=actor.id,
        )
        self.session.add(document)
        self.session.commit()

        try:
            extracted = extract_document(
                name, content,
                max_chars=self.limits.max_extracted_chars, max_pdf_pages=self.limits.max_pdf_pages,
            )
            chunks = chunk_text(
                extracted.text, max_chars=self.limits.chunk_chars, overlap=self.limits.chunk_overlap,
            )
            if not chunks:
                raise ExtractionError("no_text", "В документе нет текста, который можно прочитать.")
            for chunk in chunks:
                document.chunks.append(KnowledgeChunk(
                    position=chunk.position,
                    text=chunk.text,
                    char_count=chunk.char_count,
                    token_count=chunk.token_count,
                    chunk_metadata={"heading": chunk.heading, "start": chunk.start, "end": chunk.end},
                ))
            document.extracted_chars = len(extracted.text)
            document.status = "ready"
        except ExtractionError as error:
            document.status = "failed"
            document.error_message = error.message
        except Exception:  # an unexpected parser crash must not leave the document "processing"
            logger.exception("knowledge.processing_failed document_id=%s", document.id)
            document.chunks.clear()
            document.status = "failed"
            document.error_message = "Не удалось обработать документ. Попробуйте другой файл."
        document.processed_at = utc_now()
        self._audit(actor, "knowledge.document_uploaded", document)
        self.session.commit()
        return self.get(document.id)

    def delete(self, document_id: str, actor: User) -> None:
        document = self.get(document_id)
        self._audit(actor, "knowledge.document_deleted", document)
        self.session.delete(document)
        self.session.commit()

    def _audit(self, actor: User, action: str, document: KnowledgeDocument) -> None:
        # Metadata only: document text never goes to the audit log.
        self.session.add(AdminAuditEvent(actor_id=actor.id, action=action, changes={
            "document_id": document.id,
            "title": document.title,
            "original_filename": document.original_filename,
            "sha256": document.sha256,
            "size_bytes": document.size_bytes,
            "status": document.status,
            "chunk_count": len(document.chunks),
        }))


def _clean_label(value: str | None, limit: int) -> str | None:
    cleaned = " ".join((value or "").split())[:limit]
    return cleaned or None
