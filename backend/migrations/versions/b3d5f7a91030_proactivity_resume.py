"""Track completion of an accepted proactive action across browser sessions."""
import sqlalchemy as sa
from alembic import op

revision = "b3d5f7a91030"
down_revision = "a2c4e6f81030"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("proactive_items", sa.Column("action_completed_at", sa.DateTime(), nullable=True))
    # Previously accepted items were delivered under the original, non-recoverable protocol.
    op.execute("UPDATE proactive_items SET action_completed_at = COALESCE(resolved_at, created_at) WHERE status = 'accepted'")


def downgrade():
    op.drop_column("proactive_items", "action_completed_at")
