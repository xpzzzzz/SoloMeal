"""Separate purchased checks from inventory confirmation."""
import sqlalchemy as sa
from alembic import op

revision = "a7c9e2f10463"
down_revision = "f5a8c2d7e901"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("shopping_lists", sa.Column("checked_ingredient_ids", sa.JSON(), nullable=True))
    op.execute("UPDATE shopping_lists SET checked_ingredient_ids = '[]'")
    with op.batch_alter_table("shopping_lists") as batch:
        batch.alter_column("checked_ingredient_ids", existing_type=sa.JSON(), nullable=False)


def downgrade():
    op.drop_column("shopping_lists", "checked_ingredient_ids")
