"""Avoid MySQL rounding an immediately available task into the future."""
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import DATETIME
from alembic import context, op

revision = "e0a6c8d21015"
down_revision = "d9e4a6b81015"
branch_labels = None
depends_on = None
REQUIRED = ("deadline_at", "available_at", "dispatch_after", "created_at")
OPTIONAL = ("publish_until", "dispatched_at", "lease_until", "finished_at")


def upgrade():
    # SQLite already preserves microseconds; avoid rebuilding FK-linked tables there.
    if op.get_bind().dialect.name != "mysql":
        return
    target = DATETIME(fsp=6)
    existing = {} if context.is_offline_mode() else {
        column['name']: getattr(column['type'], 'fsp', None)
        for column in sa.inspect(op.get_bind()).get_columns('receipt_parse_tasks')
    }
    for name in REQUIRED + OPTIONAL:
        if existing.get(name) == 6:
            continue
        op.alter_column("receipt_parse_tasks", name, existing_type=sa.DateTime(),
                        type_=target, existing_nullable=name in OPTIONAL)
    columns = [] if context.is_offline_mode() else sa.inspect(op.get_bind()).get_columns('receipt_imports')
    if not any(c['name'] == 'parse_deadline_at' and getattr(c['type'], 'fsp', None) == 6 for c in columns):
        op.alter_column("receipt_imports", "parse_deadline_at", existing_type=sa.DateTime(),
                        type_=target, existing_nullable=True)


def downgrade():
    # Precision six is backward compatible with d9 and avoids destroying stored fractions.
    # Fresh d9 creation already uses it; this revision only repairs earlier local d9 tables.
    pass
