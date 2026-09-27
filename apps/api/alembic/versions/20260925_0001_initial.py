"""Create dialogue persistence tables."""

from collections.abc import Sequence

from alembic import context, op
import sqlalchemy as sa

revision: str = "20260925_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


EXPECTED_COLUMNS = {
    "conversations": {
        "id",
        "status",
        "created_at",
        "updated_at",
        "summary",
        "service",
        "symptoms",
        "urgency",
        "urgency_reason",
        "known_facts",
        "missing_facts",
        "confidence",
        "playbook_id",
        "current_step_code",
        "current_step_instruction",
        "escalation_summary",
        "incident_id",
    },
    "messages": {"id", "conversation_id", "role", "content", "created_at"},
    "troubleshooting_steps": {
        "id",
        "conversation_id",
        "code",
        "instruction",
        "outcome",
        "position",
        "created_at",
    },
}

EXPECTED_INDEXES = {
    "conversations": {"ix_conversations_status", "ix_conversations_urgency"},
    "messages": {"ix_messages_conversation_id"},
    "troubleshooting_steps": {"ix_troubleshooting_steps_conversation_id"},
}


def _validate_legacy_schema(inspector: sa.Inspector) -> None:
    problems: list[str] = []
    existing_tables = set(inspector.get_table_names())

    for table, expected_columns in EXPECTED_COLUMNS.items():
        if table not in existing_tables:
            problems.append(f"missing table {table}")
            continue
        actual_columns = {column["name"] for column in inspector.get_columns(table)}
        missing_columns = expected_columns - actual_columns
        if missing_columns:
            problems.append(f"{table} missing columns: {', '.join(sorted(missing_columns))}")

        actual_indexes = {
            index["name"] for index in inspector.get_indexes(table) if index.get("name")
        }
        missing_indexes = EXPECTED_INDEXES[table] - actual_indexes
        if missing_indexes:
            problems.append(f"{table} missing indexes: {', '.join(sorted(missing_indexes))}")

    for table in ("messages", "troubleshooting_steps"):
        if table not in existing_tables:
            continue
        foreign_keys = inspector.get_foreign_keys(table)
        has_conversation_fk = any(
            fk.get("referred_table") == "conversations"
            and fk.get("constrained_columns") == ["conversation_id"]
            and fk.get("referred_columns") == ["id"]
            for fk in foreign_keys
        )
        if not has_conversation_fk:
            problems.append(f"{table} missing conversation foreign key")

    if problems:
        details = "; ".join(problems)
        raise RuntimeError(f"incompatible pre-Alembic schema; {details}")


def upgrade() -> None:
    # Early demo builds used SQLAlchemy create_all(). Adopt that matching
    # schema so existing local/Docker data can receive future migrations.
    if not context.is_offline_mode():
        inspector = sa.inspect(op.get_bind())
        if "conversations" in inspector.get_table_names():
            _validate_legacy_schema(inspector)
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
