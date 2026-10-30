"""Persistent receipt execution and outbox, without changing historical attempts."""
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import DATETIME
from alembic import op

revision = "d9e4a6b81015"
down_revision = "a7c9e2f10463"
branch_labels = None
depends_on = None
TIME = sa.DateTime().with_variant(DATETIME(fsp=6), "mysql")


def upgrade():
    op.add_column("receipt_imports", sa.Column("parse_task_id", sa.String(36), nullable=True))
    op.add_column("receipt_imports", sa.Column("parse_deadline_at", TIME, nullable=True))
    op.add_column("receipt_imports", sa.Column("parse_error", sa.String(32), nullable=True))
    op.create_table(
        "receipt_parse_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("receipt_id", sa.String(36), sa.ForeignKey("receipt_imports.id"), nullable=False, unique=True),
        sa.Column("operation_id", sa.String(36), sa.ForeignKey("operations.id"), nullable=False, unique=True),
        sa.Column("expected_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("deadline_at", TIME, nullable=False),
        sa.Column("available_at", TIME, nullable=False),
        sa.Column("dispatch_after", TIME, nullable=False),
        sa.Column("publish_token", sa.String(36), nullable=True),
        sa.Column("publish_until", TIME, nullable=True),
        sa.Column("dispatch_attempts", sa.Integer(), nullable=False),
        sa.Column("dispatched_at", TIME, nullable=True),
        sa.Column("lease_token", sa.String(36), nullable=True),
        sa.Column("lease_until", TIME, nullable=True),
        sa.Column("last_error", sa.String(32), nullable=True),
        sa.Column("finished_at", TIME, nullable=True),
        sa.Column("created_at", TIME, nullable=False),
    )
    op.create_index("ix_receipt_parse_tasks_user_id", "receipt_parse_tasks", ["user_id"])
    op.create_index("ix_receipt_task_dispatch", "receipt_parse_tasks", ["status", "dispatch_after"])
    op.create_index("ix_receipt_task_lease", "receipt_parse_tasks", ["status", "lease_until"])


def downgrade():
    op.drop_table("receipt_parse_tasks")
    for column in ("parse_error", "parse_deadline_at", "parse_task_id"):
        op.drop_column("receipt_imports", column)
