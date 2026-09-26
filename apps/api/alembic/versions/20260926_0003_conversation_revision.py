"""Optimistic concurrency control for dialogue turns."""

from alembic import context, op
import sqlalchemy as sa

revision = "20260926_0003"
down_revision = "20260926_0002"
branch_labels = None
depends_on = None


def upgrade():
    if not context.is_offline_mode():
        columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("conversations")}
        if "revision" in columns:
            return
    op.add_column("conversations", sa.Column("revision", sa.Integer(), nullable=False, server_default="1"))


def downgrade():
    with op.batch_alter_table("conversations") as batch:
        batch.drop_column("revision")
