"""Add operator assignment, lifecycle timestamps, ratings and invite metadata."""

from alembic import context, op
import sqlalchemy as sa


revision = "20260927_0006"
down_revision = "20260927_0005"
branch_labels = None
depends_on = None

CONVERSATION_COLUMNS = [
    ("assignee_id", sa.String(36)),
    ("escalated_at", sa.DateTime(timezone=True)),
    ("assigned_at", sa.DateTime(timezone=True)),
    ("first_operator_reply_at", sa.DateTime(timezone=True)),
    ("resolved_at", sa.DateTime(timezone=True)),
    ("resolved_by", sa.String(16)),
    ("rating", sa.Integer()),
    ("rating_comment", sa.Text()),
]
INVITE_COLUMNS = [
    ("first_name", sa.String(50)),
    ("last_name", sa.String(50)),
    ("invited_by_id", sa.String(36)),
]


def _columns(inspector, table):
    return set() if inspector is None else {column["name"] for column in inspector.get_columns(table)}


def upgrade():
    inspector = None if context.is_offline_mode() else sa.inspect(op.get_bind())
    is_postgres = op.get_context().dialect.name == "postgresql"

    existing = _columns(inspector, "conversations")
    for name, type_ in CONVERSATION_COLUMNS:
        if name not in existing:
            op.add_column("conversations", sa.Column(name, type_, nullable=True))
    if "assignee_id" not in existing:
        op.create_index("ix_conversations_assignee_id", "conversations", ["assignee_id"])
        op.create_index("ix_conversations_resolved_at", "conversations", ["resolved_at"])
        if is_postgres:
            op.create_foreign_key("fk_conversations_assignee_id_users", "conversations", "users",
                                  ["assignee_id"], ["id"], ondelete="SET NULL")

    if "author_id" not in _columns(inspector, "messages"):
        op.add_column("messages", sa.Column("author_id", sa.String(36), nullable=True))
        if is_postgres:
            op.create_foreign_key("fk_messages_author_id_users", "messages", "users",
                                  ["author_id"], ["id"], ondelete="SET NULL")

    existing = _columns(inspector, "operator_invites")
    for name, type_ in INVITE_COLUMNS:
        if name not in existing:
            op.add_column("operator_invites", sa.Column(name, type_, nullable=True))


def downgrade():
    with op.batch_alter_table("operator_invites") as batch:
        for name, _ in reversed(INVITE_COLUMNS):
            batch.drop_column(name)
    with op.batch_alter_table("messages") as batch:
        batch.drop_column("author_id")
    op.drop_index("ix_conversations_resolved_at", table_name="conversations")
    op.drop_index("ix_conversations_assignee_id", table_name="conversations")
    with op.batch_alter_table("conversations") as batch:
        for name, _ in reversed(CONVERSATION_COLUMNS):
            batch.drop_column(name)
