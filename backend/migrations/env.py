from alembic import context
from app.core.config import Settings
from app.core.database import Base
from app.models import agent, discovery, food, identity, plans, receipts, shopping  # noqa: F401
from sqlalchemy import create_engine, pool

url = Settings().database_url
if context.is_offline_mode():
    context.configure(url=url, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
