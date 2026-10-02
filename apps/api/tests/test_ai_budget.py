"""Synthetic global budget tests: no paid provider calls or private player data."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.ai.budget import (
    REQUEST_HOLD_USD,
    BudgetExhausted,
    BudgetService,
    UnknownModelPricing,
    estimated_cost,
    price_for,
)
from app.models.tables import AiProviderRequest, AiRun
from sqlalchemy import select
from test_ai_analyst import FakeProvider, _player
from test_phase2_api import OTHER, OWNER, _auth

pytest_plugins = ("test_phase2_api",)


def _run(database, actor: UUID, player_id: str) -> UUID:
    with database.user_transaction(actor) as session:
        run = AiRun(
            player_id=UUID(player_id),
            actor_user_id=actor,
            kind="chat",
            status="pending",
            provider="openai",
            model="gpt-6-luna",
            prompt_version="analyst_v1",
            analytics_rule_version="analytics_v1",
            data_fingerprint="f" * 64,
            evidence_snapshot={},
        )
        session.add(run)
        session.flush()
        return run.id


def _spent(database, actor: UUID, run_id: UUID, amount: str, when: datetime | None = None) -> None:
    with database.user_transaction(actor) as session:
        session.add(
            AiProviderRequest(
                ai_run_id=run_id,
                budget_month=(when or datetime.now(UTC)).date().replace(day=1),
                model="gpt-6-luna",
                pricing_version=price_for("gpt-6-luna").version,
                status="completed",
                reserved_cost_usd=Decimal(0),
                estimated_cost_usd=Decimal(amount),
                input_tokens=100,
                output_tokens=50,
            )
        )


def test_decimal_pricing_and_unknown_model_fail_closed() -> None:
    assert estimated_cost("gpt-6-luna", 1_000_000, 1_000_000) == Decimal("0.600000000")
    assert estimated_cost("gpt-6-luna", 1617, 260) == Decimal("0.000291700")
    with pytest.raises(UnknownModelPricing):
        estimated_cost("unknown-model", 0, 0)


def test_zero_low_and_global_cross_actor_usage(phase2) -> None:
    client, database, _, settings = phase2
    first_player = _player(client)
    second = client.post("/v1/players", headers=_auth("other"), json={"display_name": "Second synthetic player"})
    assert second.status_code == 201
    first_run = _run(database, OWNER, first_player)
    second_run = _run(database, OTHER, second.json()["id"])
    owner_budget = BudgetService(database, settings, OWNER)
    other_budget = BudgetService(database, settings, OTHER)
    empty = owner_budget.summary()
    assert empty.estimated_spend_usd == 0 and empty.usable_budget_usd == Decimal("4.90")
    reservation = owner_budget.reserve(first_run, "gpt-6-luna")
    assert owner_budget.summary().estimated_spend_usd == REQUEST_HOLD_USD
    owner_budget.settle(reservation, "gpt-6-luna", 1000, 100)
    low = other_budget.summary()
    assert low.estimated_spend_usd == estimated_cost("gpt-6-luna", 1000, 100)
    assert low.provider_request_count == 1 and low.input_tokens == 1000 and low.output_tokens == 100
    assert other_budget.reserve(second_run, "gpt-6-luna")
    _spent(database, OWNER, first_run, "4.900000")
    with pytest.raises(BudgetExhausted):
        other_budget.reserve(second_run, "gpt-6-luna")
    assert other_budget.summary().estimated_spend_usd > Decimal("4.90")


@pytest.mark.parametrize("amount", ["4.900000", "5.000000", "5.500000"])
def test_reserve_threshold_and_above_budget_block(phase2, amount: str) -> None:
    client, database, _, settings = phase2
    run_id = _run(database, OWNER, _player(client))
    _spent(database, OWNER, run_id, amount)
    with pytest.raises(BudgetExhausted):
        BudgetService(database, settings, OWNER).reserve(run_id, "gpt-6-luna")


def test_reservation_can_fill_usable_budget_exactly(phase2) -> None:
    client, database, _, settings = phase2
    run_id = _run(database, OWNER, _player(client))
    _spent(database, OWNER, run_id, "4.890000000")
    budget = BudgetService(database, settings, OWNER)
    assert budget.reserve(run_id, "gpt-6-luna")
    assert budget.summary().estimated_remaining_usd == 0


def test_utc_month_rollover_retains_history(phase2) -> None:
    client, database, _, settings = phase2
    run_id = _run(database, OWNER, _player(client))
    september = datetime(2026, 9, 30, 23, 59, tzinfo=UTC)
    october = datetime(2026, 10, 1, 0, 1, tzinfo=UTC)
    _spent(database, OWNER, run_id, "4.900000", september)
    budget = BudgetService(database, settings, OWNER)
    assert budget.summary(september).estimated_spend_usd == Decimal("4.900000")
    assert budget.summary(october).estimated_spend_usd == 0
    assert budget.reserve(run_id, "gpt-6-luna", october)
    assert budget.summary(september).provider_request_count == 1


def test_later_call_is_blocked_and_non_ai_routes_continue(phase2) -> None:
    client, database, _, settings = phase2
    settings.ai_monthly_budget_usd = Decimal("0.010001")
    settings.ai_budget_reserve_usd = Decimal(0)
    player_id = _player(client)
    provider = FakeProvider(provider_name="openai")
    client.app.state.ai_provider = provider
    thread = client.post(f"/v1/players/{player_id}/chats", headers=_auth(), json={})
    response = client.post(
        f"/v1/players/{player_id}/chats/{thread.json()['id']}/messages",
        headers=_auth(),
        json={"question": "What is my speed?", "request_id": str(uuid4())},
    )
    assert response.status_code == 200
    assert response.json()["error_code"] == "ai_budget_exhausted"
    assert provider.select_count == 1 and provider.answer_count == 0
    assert BudgetService(database, settings, OWNER).summary().provider_request_count == 1
    assert client.get(f"/v1/players/{player_id}/analytics/overview", headers=_auth()).status_code == 200
    assert client.get(f"/v1/players/{player_id}/sessions", headers=_auth()).status_code == 200
    assert client.get("/v1/report-uploads", headers=_auth()).status_code == 200


def test_first_call_blocked_without_invoking_provider(phase2) -> None:
    client, database, _, settings = phase2
    player_id = _player(client)
    run_id = _run(database, OWNER, player_id)
    _spent(database, OWNER, run_id, "4.900000")
    provider = FakeProvider(provider_name="openai")
    client.app.state.ai_provider = provider
    thread = client.post(f"/v1/players/{player_id}/chats", headers=_auth(), json={})
    response = client.post(
        f"/v1/players/{player_id}/chats/{thread.json()['id']}/messages",
        headers=_auth(),
        json={"question": "What is my speed?", "request_id": str(uuid4())},
    )
    assert response.status_code == 200 and response.json()["error_code"] == "ai_budget_exhausted"
    assert provider.select_count == 0 and provider.answer_count == 0


def test_unknown_configured_model_never_calls_provider(phase2) -> None:
    client, _, _, settings = phase2
    settings.openai_model = "unreviewed-model"
    player_id = _player(client)
    provider = FakeProvider(provider_name="openai")
    client.app.state.ai_provider = provider
    thread = client.post(f"/v1/players/{player_id}/chats", headers=_auth(), json={})
    response = client.post(
        f"/v1/players/{player_id}/chats/{thread.json()['id']}/messages",
        headers=_auth(),
        json={"question": "What is my speed?", "request_id": str(uuid4())},
    )
    assert response.status_code == 200 and response.json()["error_code"] == "ai_pricing_unavailable"
    assert provider.select_count == 0 and provider.answer_count == 0


def test_actor_daily_quota_remains_independent_of_global_budget(phase2) -> None:
    client, database, _, settings = phase2
    assert settings.ai_daily_run_limit == 20
    player_id = _player(client)
    for _ in range(20):
        _run(database, OWNER, player_id)
    provider = FakeProvider(provider_name="openai")
    client.app.state.ai_provider = provider
    thread = client.post(f"/v1/players/{player_id}/chats", headers=_auth(), json={})
    response = client.post(
        f"/v1/players/{player_id}/chats/{thread.json()['id']}/messages",
        headers=_auth(),
        json={"question": "What is my speed?", "request_id": str(uuid4())},
    )
    assert response.status_code == 429 and response.json()["error"]["code"] == "ai_quota_exceeded"
    assert provider.select_count == 0
    assert BudgetService(database, settings, OWNER).summary().estimated_spend_usd == 0


def test_provider_failure_keeps_conservative_hold_and_is_not_retried(phase2) -> None:
    client, database, _, settings = phase2
    player_id = _player(client)

    class QuotaFailure(FakeProvider):
        def select(self, question, context, tools):
            self.select_count += 1
            raise RuntimeError("synthetic provider billing limit")

    provider = QuotaFailure(provider_name="openai")
    client.app.state.ai_provider = provider
    thread = client.post(f"/v1/players/{player_id}/chats", headers=_auth(), json={})
    response = client.post(
        f"/v1/players/{player_id}/chats/{thread.json()['id']}/messages",
        headers=_auth(),
        json={"question": "What is my speed?", "request_id": str(uuid4())},
    )
    assert response.status_code == 200 and response.json()["error_code"] == "provider_unavailable"
    assert provider.select_count == 1 and provider.answer_count == 0
    with database.user_transaction(OWNER) as session:
        row = session.scalar(select(AiProviderRequest))
        assert row is not None and row.status == "uncertain" and row.reserved_cost_usd == REQUEST_HOLD_USD


def test_concurrent_reservations_share_one_remaining_slot(phase2) -> None:
    client, database, _, settings = phase2
    settings.ai_monthly_budget_usd = REQUEST_HOLD_USD
    settings.ai_budget_reserve_usd = Decimal(0)
    player_id = _player(client)
    runs = [_run(database, OWNER, player_id) for _ in range(2)]
    barrier = Barrier(2)

    def attempt(run_id: UUID) -> bool:
        barrier.wait(timeout=5)
        try:
            BudgetService(database, settings, OWNER).reserve(run_id, "gpt-6-luna")
            return True
        except BudgetExhausted:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt, runs)) == [False, True]


def test_migration_chain_has_single_new_head() -> None:
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    assert script.get_heads() == ["0010_team_creation_rls"]
    assert script.get_revision("0007_global_ai_budget").down_revision == "0006_ai_analyst"
    assert script.get_revision("0008_ai_budget_precision").down_revision == "0007_global_ai_budget"
    assert script.get_revision("0010_team_creation_rls").down_revision == "0009_player_identity_teams"
