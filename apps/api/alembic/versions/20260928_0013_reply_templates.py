"""Add reply templates for specialists."""

from alembic import context, op
import sqlalchemy as sa


revision = "20260928_0013"
down_revision = "20260928_0012"
branch_labels = None
depends_on = None


def upgrade():
    # A database created by create_all already has the table: create only what is missing.
    existing = set() if context.is_offline_mode() else set(sa.inspect(op.get_bind()).get_table_names())
    if "reply_templates" in existing:
        return
    op.create_table(
        "reply_templates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_reply_templates_created_by", "reply_templates", ["created_by"])


def downgrade():
    op.drop_index("ix_reply_templates_created_by", table_name="reply_templates")
    op.drop_table("reply_templates")
