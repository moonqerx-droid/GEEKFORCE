"""Store answer provenance on each assistant message."""

from alembic import context, op
import sqlalchemy as sa


revision = "20260928_0012"
down_revision = "20260928_0010"
branch_labels = None
depends_on = None


def _message_columns() -> set[str]:
    if context.is_offline_mode():
        return set()
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns("messages")}


def upgrade():
    existing = _message_columns()
    if "answer_kind" not in existing:
        op.add_column("messages", sa.Column("answer_kind", sa.String(16), nullable=True))
    if "citations" not in existing:
        op.add_column("messages", sa.Column("citations", sa.JSON(), nullable=True))


def downgrade():
    existing = _message_columns()
    if "citations" in existing:
        op.drop_column("messages", "citations")
    if "answer_kind" in existing:
        op.drop_column("messages", "answer_kind")
