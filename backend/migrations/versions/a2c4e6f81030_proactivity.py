"""Add the proactive inbox and per-user settings."""
import sqlalchemy as sa
from alembic import op

revision = "a2c4e6f81030"
down_revision = "f1b7d9e31015"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "proactive_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("subject_key", sa.String(128), nullable=False),
        sa.Column("dedupe_key", sa.String(200), nullable=False),
        sa.Column("delivery_slot", sa.String(16), nullable=False),
        sa.Column("priority", sa.SmallInteger(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.String(500), nullable=False),
        sa.Column("why", sa.String(300), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("snapshot_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("delivered_at", sa.DateTime()),
        sa.Column("resolved_at", sa.DateTime()),
        sa.Column("expires_at", sa.DateTime()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("user_id", "dedupe_key", name="uq_proactive_dedupe"),
        sa.UniqueConstraint("user_id", "delivery_slot", name="uq_proactive_daily_slot"),
    )
    op.create_index("ix_proactive_items_user_id", "proactive_items", ["user_id"])
    op.create_index("ix_proactive_inbox", "proactive_items", ["user_id", "status", "priority", "created_at"])
    op.create_table(
        "proactive_settings",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("daily_limit", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("quiet_start", sa.String(5), nullable=False, server_default="22:00"),
        sa.Column("quiet_end", sa.String(5), nullable=False, server_default="08:00"),
        sa.Column("snooze_until", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade():
    op.drop_table("proactive_settings")
    op.drop_index("ix_proactive_inbox", table_name="proactive_items")
    op.drop_index("ix_proactive_items_user_id", table_name="proactive_items")
    op.drop_table("proactive_items")
