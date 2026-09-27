"""Persist grounded-answer sources, fallback reason and model latency."""

from alembic import context, op
import sqlalchemy as sa

revision = "20260926_0004"
down_revision = "20260926_0003"
branch_labels = None
depends_on = None


def upgrade():
    existing = set() if context.is_offline_mode() else {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("conversations")
    }
    columns = [
        sa.Column("rag_source_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("ai_fallback_reason", sa.String(80), nullable=True),
        sa.Column("ai_latency_ms", sa.Integer(), nullable=True),
    ]
    for column in columns:
        if column.name not in existing:
            op.add_column("conversations", column)


def downgrade():
    with op.batch_alter_table("conversations") as batch:
        for name in ("ai_latency_ms", "ai_fallback_reason", "rag_source_ids"):
            batch.drop_column(name)
