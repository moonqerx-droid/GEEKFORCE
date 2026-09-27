"""Add users, sessions, email tokens, operator invites and conversation ownership."""

from alembic import context, op
import sqlalchemy as sa


revision = "20260927_0005"
down_revision = "20260926_0004"
branch_labels = None
depends_on = None


def upgrade():
    inspector = None if context.is_offline_mode() else sa.inspect(op.get_bind())
    existing_tables = set() if inspector is None else set(inspector.get_table_names())

    if "users" not in existing_tables:
        op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("first_name", sa.String(50), nullable=False),
        sa.Column("last_name", sa.String(50), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("department", sa.String(32), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("email", name="uq_users_email"),
        )
        op.create_index("ix_users_email", "users", ["email"])
        op.create_index("ix_users_role", "users", ["role"])

    if "auth_sessions" not in existing_tables:
        op.create_table(
        "auth_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.String(300), nullable=True),
        sa.Column("ip_hash", sa.String(64), nullable=True),
        )
        op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
        op.create_index("ix_auth_sessions_token_hash", "auth_sessions", ["token_hash"], unique=True)
        op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])
    if "email_tokens" not in existing_tables:
        op.create_table(
        "email_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("purpose", sa.String(24), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_email_tokens_user_id", "email_tokens", ["user_id"])
        op.create_index("ix_email_tokens_purpose", "email_tokens", ["purpose"])
        op.create_index("ix_email_tokens_token_hash", "email_tokens", ["token_hash"], unique=True)
        op.create_index("ix_email_tokens_expires_at", "email_tokens", ["expires_at"])
    if "operator_invites" not in existing_tables:
        op.create_table(
        "operator_invites",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_operator_invites_email", "operator_invites", ["email"])
        op.create_index("ix_operator_invites_token_hash", "operator_invites", ["token_hash"], unique=True)
        op.create_index("ix_operator_invites_expires_at", "operator_invites", ["expires_at"])

    conversation_columns = set() if inspector is None else {
        column["name"] for column in inspector.get_columns("conversations")
    }
    if "owner_id" not in conversation_columns:
        op.add_column("conversations", sa.Column("owner_id", sa.String(36), nullable=True))
        op.create_index("ix_conversations_owner_id", "conversations", ["owner_id"])
        if not context.is_offline_mode():
            with op.batch_alter_table("conversations") as batch:
                batch.create_foreign_key(
                    "fk_conversations_owner", "users", ["owner_id"], ["id"], ondelete="SET NULL"
                )


def downgrade():
    with op.batch_alter_table("conversations") as batch:
        batch.drop_index("ix_conversations_owner_id")
        batch.drop_constraint("fk_conversations_owner", type_="foreignkey")
        batch.drop_column("owner_id")
    op.drop_table("operator_invites")
    op.drop_table("email_tokens")
    op.drop_table("auth_sessions")
    op.drop_table("users")
