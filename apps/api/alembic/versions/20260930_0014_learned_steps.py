"""Add steps learned from closed requests."""

from alembic import context, op
import sqlalchemy as sa


revision = "20260930_0014"
down_revision = "20260928_0013"
branch_labels = None
depends_on = None


def upgrade():
    # A database created by create_all already has the table: create only what is missing.
    existing = set() if context.is_offline_mode() else set(sa.inspect(op.get_bind()).get_table_names())
    if "learned_steps" in existing:
        return
    op.create_table(
        "learned_steps",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("playbook_id", sa.String(120), nullable=False),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column("source_conversation_id", sa.String(36), nullable=True),
        sa.Column("source_resolution", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_learned_steps_playbook_id", "learned_steps", ["playbook_id"])
    op.create_index("ix_learned_steps_source_conversation_id", "learned_steps", ["source_conversation_id"])
    op.create_index("ix_learned_steps_created_by", "learned_steps", ["created_by"])


def downgrade():
    op.drop_index("ix_learned_steps_created_by", table_name="learned_steps")
    op.drop_index("ix_learned_steps_source_conversation_id", table_name="learned_steps")
    op.drop_index("ix_learned_steps_playbook_id", table_name="learned_steps")
    op.drop_table("learned_steps")
