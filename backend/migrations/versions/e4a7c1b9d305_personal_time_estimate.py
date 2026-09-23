"""Personal cooking-time estimate switch, on by default for every existing account."""

import sqlalchemy as sa
from alembic import op

revision = "e4a7c1b9d305"
down_revision = "c63a1e7d9f20"
branch_labels = None
depends_on = None


def upgrade():
    # Existing users keep the behaviour they had: no one is opted into personal estimates silently.
    op.add_column("user_preferences",
                  sa.Column("personal_time_enabled", sa.Boolean(), nullable=False, server_default="1"))


def downgrade():
    op.drop_column("user_preferences", "personal_time_enabled")
