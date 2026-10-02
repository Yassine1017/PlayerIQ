"""Verify portable coordination without privileges on source tables."""

from types import SimpleNamespace
from unittest.mock import Mock

from app.services.transaction_locks import lock_resource


def test_postgres_resource_locks_are_stable_and_namespaced() -> None:
    session = Mock()
    session.get_bind.return_value = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    lock_resource(session, "player-session", "synthetic-id")
    lock_resource(session, "player-session", "synthetic-id")
    lock_resource(session, "source-row", "synthetic-id")
    calls = session.execute.call_args_list
    assert all(str(call.args[0]) == "SELECT pg_advisory_xact_lock(:key)" for call in calls)
    assert calls[0].args[1] == calls[1].args[1]
    assert calls[0].args[1] != calls[2].args[1]
    assert all(-(2**63) <= call.args[1]["key"] < 2**63 for call in calls)


def test_sqlite_does_not_receive_postgres_lock_sql() -> None:
    session = Mock()
    session.get_bind.return_value = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    lock_resource(session, "player-session", "synthetic-id")
    session.execute.assert_not_called()
