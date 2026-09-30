"""«Помощь коллег»: лента просьб, чат с помощником, личные сообщения и счётчик помощи."""

from alembic import context, op
import sqlalchemy as sa


revision = "20261001_0015"
down_revision = "20260930_0014"
branch_labels = None
depends_on = None


def _inspector():
    return None if context.is_offline_mode() else sa.inspect(op.get_bind())


def upgrade():
    # A database created by create_all already has everything: add only what is missing.
    inspector = _inspector()
    tables = set() if inspector is None else set(inspector.get_table_names())
    user_columns = set() if inspector is None else {c["name"] for c in inspector.get_columns("users")}

    if "helped_count" not in user_columns:
        op.add_column("users", sa.Column("helped_count", sa.Integer(), nullable=False, server_default="0"))

    if "peer_help_requests" not in tables:
        op.create_table(
            "peer_help_requests",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("conversation_id", sa.String(36),
                      sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, unique=True),
            sa.Column("author_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("helper_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("title", sa.String(300), nullable=False),
            sa.Column("area", sa.String(120), nullable=False),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_peer_help_requests_conversation_id", "peer_help_requests", ["conversation_id"], unique=True)
        op.create_index("ix_peer_help_requests_author_id", "peer_help_requests", ["author_id"])
        op.create_index("ix_peer_help_requests_helper_id", "peer_help_requests", ["helper_id"])
        op.create_index("ix_peer_help_requests_status", "peer_help_requests", ["status"])

    if "peer_help_messages" not in tables:
        op.create_table(
            "peer_help_messages",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("peer_help_request_id", sa.String(36),
                      sa.ForeignKey("peer_help_requests.id", ondelete="CASCADE"), nullable=False),
            sa.Column("sender_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_peer_help_messages_peer_help_request_id", "peer_help_messages", ["peer_help_request_id"])
        op.create_index("ix_peer_help_messages_sender_id", "peer_help_messages", ["sender_id"])

    if "direct_messages" not in tables:
        op.create_table(
            "direct_messages",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("sender_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("recipient_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_direct_messages_sender_id", "direct_messages", ["sender_id"])
        op.create_index("ix_direct_messages_recipient_id", "direct_messages", ["recipient_id"])


def downgrade():
    op.drop_table("direct_messages")
    op.drop_table("peer_help_messages")
    op.drop_table("peer_help_requests")
    inspector = _inspector()
    if inspector is not None and "helped_count" in {c["name"] for c in inspector.get_columns("users")}:
        with op.batch_alter_table("users") as batch:
            batch.drop_column("helped_count")
