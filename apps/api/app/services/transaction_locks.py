"""Transaction-scoped coordination without write grants on immutable evidence."""

from hashlib import sha256

from sqlalchemy import text
from sqlalchemy.orm import Session


def lock_resource(session: Session, namespace: str, resource: str) -> None:
    """Serialize a resource on PostgreSQL; authorization remains with callers.

    A stable signed bigint works across processes and transaction poolers. A hash
    collision only serializes unrelated work. The lock is released on commit or
    rollback and never grants table access. SQLite tests run single-threaded.
    """
    if session.get_bind().dialect.name != "postgresql":
        return
    key = int.from_bytes(sha256(f"playeriq:{namespace}:{resource}".encode()).digest()[:8], "big", signed=True)
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
