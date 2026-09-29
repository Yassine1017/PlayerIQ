"""Alembic environment for the private PlayerIQ PostgreSQL schema."""

import app.models  # noqa: F401 - register mapped tables
from alembic import context
from app.core.config import get_settings
from app.db.base import Base
from sqlalchemy import create_engine, pool

target_metadata = Base.metadata


def include_object(object_, name, type_, reflected, compare_to):  # type: ignore[no-untyped-def]
    return not getattr(object_, "info", {}).get("external", False)


def database_url() -> str:
    url = get_settings().database_url
    if not url:
        raise RuntimeError("Set DATABASE_URL before running Alembic")
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        include_schemas=True,
        include_object=include_object,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
