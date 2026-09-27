from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.knowledge import KnowledgeChunk, KnowledgeDocument


class KnowledgeRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_documents(self) -> list[KnowledgeDocument]:
        return list(self.session.scalars(
            select(KnowledgeDocument)
            .options(selectinload(KnowledgeDocument.chunks), selectinload(KnowledgeDocument.uploader))
            .order_by(KnowledgeDocument.created_at.desc(), KnowledgeDocument.id)
        ).all())

    def get(self, document_id: str) -> KnowledgeDocument | None:
        return self.session.scalar(
            select(KnowledgeDocument)
            .where(KnowledgeDocument.id == document_id)
            .options(selectinload(KnowledgeDocument.chunks), selectinload(KnowledgeDocument.uploader))
        )

    def find_active_duplicate(self, digest: str) -> KnowledgeDocument | None:
        """A processing or ready document with the same content. Failed ones may be retried."""
        return self.session.scalar(
            select(KnowledgeDocument)
            .where(KnowledgeDocument.sha256 == digest, KnowledgeDocument.status != "failed")
            .order_by(KnowledgeDocument.created_at)
        )

    def ready_chunks(self) -> list[tuple[KnowledgeDocument, KnowledgeChunk]]:
        """Chunks of ready documents in a stable order: oldest document first, then position."""
        rows = self.session.execute(
            select(KnowledgeDocument, KnowledgeChunk)
            .join(KnowledgeChunk, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .where(KnowledgeDocument.status == "ready")
            .order_by(KnowledgeDocument.created_at, KnowledgeDocument.id, KnowledgeChunk.position)
        ).all()
        return [(document, chunk) for document, chunk in rows]
