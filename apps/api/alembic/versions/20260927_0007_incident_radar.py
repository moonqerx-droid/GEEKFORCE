"""Add Incident Radar clusters and broadcast history."""

from alembic import context, op
import sqlalchemy as sa


revision = "20260927_0007"
down_revision = "20260927_0006"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    if context.is_offline_mode():
        return set()
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade():
    # A database created by create_all already has the tables: create only what is missing.
    existing = _tables()
    if "incidents" not in existing:
        op.create_table(
            "incidents",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("status", sa.String(32), nullable=False, server_default="CANDIDATE"),
            sa.Column("service", sa.String(120), nullable=False),
            sa.Column("title", sa.Text(), nullable=False),
            sa.Column("signature_tokens", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("similarity_threshold", sa.Float(), nullable=False, server_default="0.55"),
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_incidents_status_service", "incidents", ["status", "service"])
    if "incident_updates" not in existing:
        op.create_table(
            "incident_updates",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "incident_id",
                sa.String(36),
                sa.ForeignKey("incidents.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("request_key", sa.String(120), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("incident_id", "request_key", name="uq_incident_updates_request_key"),
        )
        op.create_index("ix_incident_updates_incident_id", "incident_updates", ["incident_id"])


def downgrade():
    op.drop_index("ix_incident_updates_incident_id", table_name="incident_updates")
    op.drop_table("incident_updates")
    op.drop_index("ix_incidents_status_service", table_name="incidents")
    op.drop_table("incidents")
