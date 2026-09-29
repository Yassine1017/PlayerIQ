"""Database connection factories; importing this module never opens a connection."""

from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def make_engine(url: str | None = None) -> Engine:
    resolved = url or get_settings().database_url
    if not resolved:
        raise RuntimeError("DATABASE_URL is required for database operations")
    return create_engine(resolved, pool_pre_ping=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    with factory.begin() as session:
        yield session
