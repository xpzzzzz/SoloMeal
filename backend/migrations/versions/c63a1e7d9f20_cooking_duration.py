"""Optional actual cooking duration; existing records stay unknown."""
import sqlalchemy as sa
from alembic import op

revision = "c63a1e7d9f20"
down_revision = "b52e9c4a7d18"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("cooking_records", sa.Column("actual_minutes", sa.Integer(), nullable=True))
    op.add_column("cooking_records", sa.Column("duration_source", sa.String(8), nullable=True))
    op.add_column("cooking_records", sa.Column("feedback_version", sa.Integer(), nullable=False, server_default="1"))


def downgrade():
    op.drop_column("cooking_records", "feedback_version")
    op.drop_column("cooking_records", "duration_source")
    op.drop_column("cooking_records", "actual_minutes")
