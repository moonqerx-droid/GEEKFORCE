"""Add managed account state and administrative audit events."""

from alembic import context, op
import sqlalchemy as sa


revision = "20260928_0007"
down_revision = "20260927_0006"
branch_labels = None
depends_on = None


def _columns(inspector, table):
    return set() if inspector is None else {column["name"] for column in inspector.get_columns(table)}


def upgrade():
    inspector = None if context.is_offline_mode() else sa.inspect(op.get_bind())
    columns = _columns(inspector, "users")
    if "must_change_password" not in columns:
        op.add_column("users", sa.Column(
            "must_change_password", sa.Boolean(), nullable=False, server_default=sa.false(),
        ))
    if "revision" not in columns:
        op.add_column("users", sa.Column("revision", sa.Integer(), nullable=False, server_default="1"))
    tables = set() if inspector is None else set(inspector.get_table_names())
    if "admin_audit_events" not in tables:
        op.create_table(
            "admin_audit_events",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("target_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("action", sa.String(48), nullable=False),
            sa.Column("changes", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_admin_audit_events_actor_id", "admin_audit_events", ["actor_id"])
        op.create_index("ix_admin_audit_events_target_user_id", "admin_audit_events", ["target_user_id"])
        op.create_index("ix_admin_audit_events_action", "admin_audit_events", ["action"])
        op.create_index("ix_admin_audit_events_created_at", "admin_audit_events", ["created_at"])


def downgrade():
    op.drop_table("admin_audit_events")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("revision")
        batch.drop_column("must_change_password")
