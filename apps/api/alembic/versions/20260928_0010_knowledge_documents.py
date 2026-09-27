"""Add company knowledge documents and their chunks."""

from alembic import context, op
import sqlalchemy as sa


revision = "20260928_0010"
down_revision = "20260928_0009"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    if context.is_offline_mode():
        return set()
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade():
    # A database created by create_all already has the tables: create only what is missing.
    existing = _tables()
    if "knowledge_documents" not in existing:
        op.create_table(
            "knowledge_documents",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("original_filename", sa.String(160), nullable=False),
            sa.Column("media_type", sa.String(120), nullable=False),
            sa.Column("size_bytes", sa.Integer(), nullable=False),
            sa.Column("sha256", sa.String(64), nullable=False),
            sa.Column("service", sa.String(120), nullable=True),
            sa.Column("status", sa.String(16), nullable=False, server_default="processing"),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("extracted_chars", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("uploaded_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
            sa.CheckConstraint("status IN ('processing', 'ready', 'failed')", name="ck_knowledge_documents_status"),
            sa.CheckConstraint("size_bytes >= 0", name="ck_knowledge_documents_size"),
        )
        op.create_index("ix_knowledge_documents_sha256", "knowledge_documents", ["sha256"])
        op.create_index("ix_knowledge_documents_status", "knowledge_documents", ["status"])
        op.create_index("ix_knowledge_documents_created_at", "knowledge_documents", ["created_at"])
        op.create_index("ix_knowledge_documents_uploaded_by", "knowledge_documents", ["uploaded_by"])
    if "knowledge_chunks" not in existing:
        op.create_table(
            "knowledge_chunks",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "document_id", sa.String(36),
                sa.ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False,
            ),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("char_count", sa.Integer(), nullable=False),
            sa.Column("token_count", sa.Integer(), nullable=False),
            sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("document_id", "position", name="uq_knowledge_chunks_document_position"),
            sa.CheckConstraint("position >= 0", name="ck_knowledge_chunks_position"),
            sa.CheckConstraint("char_count > 0", name="ck_knowledge_chunks_not_empty"),
        )
        op.create_index("ix_knowledge_chunks_document_id", "knowledge_chunks", ["document_id"])


def downgrade():
    op.drop_index("ix_knowledge_chunks_document_id", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
    for name in (
        "ix_knowledge_documents_uploaded_by",
        "ix_knowledge_documents_created_at",
        "ix_knowledge_documents_status",
        "ix_knowledge_documents_sha256",
    ):
        op.drop_index(name, table_name="knowledge_documents")
    op.drop_table("knowledge_documents")
