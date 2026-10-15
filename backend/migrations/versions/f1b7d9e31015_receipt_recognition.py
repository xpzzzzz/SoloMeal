"""Private OCR evidence and per-task recognition mode; historical tasks remain VLM-only."""
import sqlalchemy as sa
from alembic import op

revision = "f1b7d9e31015"
down_revision = "e0a6c8d21015"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("receipt_imports", sa.Column("recognition", sa.JSON(), nullable=True))
    op.add_column("receipt_parse_tasks", sa.Column("mode", sa.String(16), nullable=False, server_default="vlm_only"))


def downgrade():
    op.drop_column("receipt_parse_tasks", "mode")
    op.drop_column("receipt_imports", "recognition")
