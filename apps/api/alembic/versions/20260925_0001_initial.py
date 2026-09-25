"""Create dialogue persistence tables."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260925_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Early demo builds used SQLAlchemy create_all(). Adopt that matching
    # schema so existing local/Docker data can receive future migrations.
    if "conversations" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("service", sa.String(length=120), nullable=True),
        sa.Column("symptoms", sa.JSON(), nullable=False),
        sa.Column("urgency", sa.String(length=16), nullable=False),
        sa.Column("urgency_reason", sa.Text(), nullable=True),
        sa.Column("known_facts", sa.JSON(), nullable=False),
        sa.Column("missing_facts", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("playbook_id", sa.String(length=120), nullable=True),
        sa.Column("current_step_code", sa.String(length=120), nullable=True),
        sa.Column("current_step_instruction", sa.Text(), nullable=True),
        sa.Column("escalation_summary", sa.Text(), nullable=True),
        sa.Column("incident_id", sa.String(length=36), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conversations_status", "conversations", ["status"])
    op.create_index("ix_conversations_urgency", "conversations", ["urgency"])
    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    op.create_table(
        "troubleshooting_steps",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=120), nullable=False),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_troubleshooting_steps_conversation_id",
        "troubleshooting_steps",
        ["conversation_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_troubleshooting_steps_conversation_id", table_name="troubleshooting_steps")
    op.drop_table("troubleshooting_steps")
    op.drop_index("ix_messages_conversation_id", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_conversations_urgency", table_name="conversations")
    op.drop_index("ix_conversations_status", table_name="conversations")
    op.drop_table("conversations")
