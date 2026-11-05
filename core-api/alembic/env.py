from alembic import context
from sqlalchemy import create_engine

from app.config import get_settings
from app.db import Base
import app.models  # noqa: F401  (register tables)

config = context.config
target_metadata = Base.metadata


def run_migrations_online() -> None:
    engine = create_engine(get_settings().DATABASE_URL)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
