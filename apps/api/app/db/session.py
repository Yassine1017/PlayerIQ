"""SQLAlchemy transaction factories with transaction-local verified actor context."""

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from fastapi import Request
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker

from app.api.errors import AppError
from app.core.config import get_settings


def normalize_database_url(raw: str) -> URL:
    url = make_url(raw)
    if url.drivername in ("postgres", "postgresql"):
        return url.set(drivername="postgresql+psycopg")
    return url


def make_engine(url: str | None = None) -> Engine:
    resolved = url or get_settings().database_url
    if not resolved:
        raise RuntimeError("DATABASE_URL is required for database operations")
    parsed = normalize_database_url(resolved)
    connect_args: dict[str, object] = {}
    if parsed.drivername == "postgresql+psycopg":
        if parsed.host and parsed.host.endswith("supabase.com") and "sslmode" not in parsed.query:
            connect_args["sslmode"] = "require"
        if parsed.port == 6543:
            connect_args["prepare_threshold"] = None
    pool_options = {"pool_size": 5, "max_overflow": 5} if parsed.drivername == "postgresql+psycopg" else {}
    return create_engine(parsed, pool_pre_ping=True, connect_args=connect_args, **pool_options)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Database:
    def __init__(self, engine: Engine, *, expected_role: str = "playeriq_api") -> None:
        if expected_role not in {"playeriq_api", "playeriq_worker"}:
            raise ValueError("Unknown PlayerIQ database role")
        self.engine = engine
        self.factory = make_session_factory(engine)
        self.expected_role = expected_role

    def _assert_restricted_role(self, session: Session) -> None:
        if self.engine.dialect.name != "postgresql":
            return
        role = session.execute(
            text(
                "SELECT r.rolsuper, r.rolbypassrls, "
                "pg_has_role(current_user, :expected_role, 'member') "
                "FROM pg_roles r WHERE r.rolname = current_user"
            ),
            {"expected_role": self.expected_role},
        ).one_or_none()
        if role is None or role[0] or role[1] or not role[2]:
            raise RuntimeError("Database login must be a restricted PlayerIQ role member")

    def check_connection(self) -> None:
        with self.factory.begin() as session:
            session.execute(text("SELECT 1"))
            self._assert_restricted_role(session)

    @contextmanager
    def user_transaction(self, user_id: UUID) -> Iterator[Session]:
        with self.factory.begin() as session:
            self._assert_restricted_role(session)
            if self.engine.dialect.name == "postgresql":
                session.execute(
                    text("SELECT set_config('playeriq.current_user_id', :user_id, true)"),
                    {"user_id": str(user_id)},
                )
            yield session

    @contextmanager
    def worker_transaction(self) -> Iterator[Session]:
        with self.factory.begin() as session:
            self._assert_restricted_role(session)
            if self.engine.dialect.name == "postgresql" and self.expected_role != "playeriq_worker":
                raise RuntimeError("Worker transaction requires worker database role")
            yield session


def get_database(request: Request) -> Database:
    database: Database | None = getattr(request.app.state, "database", None)
    if database is None:
        raise AppError("database_not_configured", "Database is not configured", 503)
    return database
