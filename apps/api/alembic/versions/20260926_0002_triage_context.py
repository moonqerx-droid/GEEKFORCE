"""Persist AI dialogue context; preserve conversations from the demo workflow."""

from alembic import context, op
import sqlalchemy as sa

revision = "20260926_0002"
down_revision = "20260925_0001"
branch_labels = None
depends_on = None


def upgrade():
    # create_all was used by early local builds and may already include these.
    existing = set() if context.is_offline_mode() else {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("conversations")
    }
    columns = [
        sa.Column("workflow_version", sa.String(20), nullable=False, server_default="legacy"),
        sa.Column("asked_facts", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("verification_failed", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("escalation_card", sa.JSON(), nullable=True),
    ]
    for column in columns:
        if column.name not in existing:
            op.add_column("conversations", column)


def downgrade():
    with op.batch_alter_table("conversations") as batch:
        for name in ("escalation_card", "verification_failed", "asked_facts", "workflow_version"):
            batch.drop_column(name)
