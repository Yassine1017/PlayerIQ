"""Global UTC-month AI budget, frozen model pricing, and per-request reservations."""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from threading import Lock
from uuid import UUID

from sqlalchemy import select, text

from app.core.config import Settings
from app.db.session import Database
from app.models.tables import AiProviderRequest, AiRun

MONEY = Decimal("0.000000001")
# The bounded Responses calls are normally far below this hold. A reservation
# protects the monthly threshold while the provider request is in flight.
REQUEST_HOLD_USD = Decimal("0.010000000")
_sqlite_lock = Lock()


@dataclass(frozen=True, slots=True)
class ModelPrice:
    version: str
    input_per_million_usd: Decimal
    output_per_million_usd: Decimal


# Reviewed 2026-09-30 against https://developers.openai.com/api/docs/models/gpt-6-luna.
# Existing request records retain their cost and pricing version when rates change.
MODEL_PRICES = {
    "gpt-6-luna": ModelPrice("gpt-6-luna-2026-09-30", Decimal("0.10"), Decimal("0.50")),
}


class UnknownModelPricing(RuntimeError):
    pass


class BudgetExhausted(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class MonthlyUsage:
    budget_month: date
    budget_usd: Decimal
    reserve_usd: Decimal
    usable_budget_usd: Decimal
    estimated_spend_usd: Decimal
    estimated_remaining_usd: Decimal
    provider_request_count: int
    input_tokens: int
    output_tokens: int


def price_for(model: str) -> ModelPrice:
    try:
        return MODEL_PRICES[model]
    except KeyError as exc:
        raise UnknownModelPricing("AI model pricing is not configured") from exc


def estimated_cost(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("Token usage cannot be negative")
    price = price_for(model)
    value = (
        Decimal(input_tokens) * price.input_per_million_usd + Decimal(output_tokens) * price.output_per_million_usd
    ) / Decimal(1_000_000)
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def utc_month(now: datetime) -> date:
    current = now.astimezone(UTC)
    return date(current.year, current.month, 1)


def _totals(rows: list[AiProviderRequest]) -> tuple[Decimal, int, int, int, bool]:
    spend = Decimal(0)
    inputs = outputs = 0
    unknown = False
    for row in rows:
        if row.status == "unknown_pricing":
            unknown = True
        elif row.status in {"reserved", "uncertain"}:
            spend += row.reserved_cost_usd
        else:
            spend += row.estimated_cost_usd or Decimal(0)
        inputs += row.input_tokens or 0
        outputs += row.output_tokens or 0
    return spend, len(rows), inputs, outputs, unknown


class BudgetService:
    def __init__(self, database: Database, settings: Settings, actor_id: UUID) -> None:
        self.database = database
        self.settings = settings
        self.actor_id = actor_id

    def _limit(self) -> Decimal:
        limit = self.settings.ai_monthly_budget_usd - self.settings.ai_budget_reserve_usd
        if limit <= 0:
            raise BudgetExhausted("Monthly AI budget is exhausted")
        return limit

    def summary(self, now: datetime | None = None) -> MonthlyUsage:
        month = utc_month(now or datetime.now(UTC))
        with self.database.user_transaction(self.actor_id) as session:
            if self.database.engine.dialect.name == "postgresql":
                result = session.execute(
                    text("SELECT * FROM playeriq.ai_budget_summary(:budget_month)"),
                    {"budget_month": month},
                ).one()
                spend, count, inputs, outputs, unknown = result
            else:
                rows = session.scalars(select(AiProviderRequest).where(AiProviderRequest.budget_month == month)).all()
                spend, count, inputs, outputs, unknown = _totals(list(rows))
        if unknown:
            raise UnknownModelPricing("Historical AI model pricing is not configured")
        budget = self.settings.ai_monthly_budget_usd
        reserve = self.settings.ai_budget_reserve_usd
        return MonthlyUsage(
            budget_month=month,
            budget_usd=budget,
            reserve_usd=reserve,
            usable_budget_usd=budget - reserve,
            estimated_spend_usd=Decimal(spend),
            estimated_remaining_usd=max(Decimal(0), budget - reserve - Decimal(spend)),
            provider_request_count=int(count),
            input_tokens=int(inputs),
            output_tokens=int(outputs),
        )

    def reserve(self, run_id: UUID, model: str, now: datetime | None = None) -> UUID:
        price = price_for(model)
        month = utc_month(now or datetime.now(UTC))
        limit = self._limit()
        if self.database.engine.dialect.name == "postgresql":
            with self.database.user_transaction(self.actor_id) as session:
                request_id = session.scalar(
                    text("SELECT playeriq.ai_budget_reserve(:run_id, :model, :price_version, :hold, :spend_limit)"),
                    {
                        "run_id": run_id,
                        "model": model,
                        "price_version": price.version,
                        "hold": REQUEST_HOLD_USD,
                        "spend_limit": limit,
                    },
                )
            if request_id is None:
                raise BudgetExhausted("Monthly AI budget is exhausted")
            return UUID(str(request_id))
        # SQLite is used only by synthetic tests. PostgreSQL uses an advisory
        # transaction lock in ai_budget_reserve for cross-process serialization.
        with _sqlite_lock, self.database.user_transaction(self.actor_id) as session:
            run = session.get(AiRun, run_id)
            if run is None or run.actor_user_id != self.actor_id or run.model != model or run.status != "pending":
                raise ValueError("AI run is not reservable")
            rows = session.scalars(select(AiProviderRequest).where(AiProviderRequest.budget_month == month)).all()
            spend, _, _, _, unknown = _totals(list(rows))
            if unknown:
                raise UnknownModelPricing("Historical AI model pricing is not configured")
            if spend + REQUEST_HOLD_USD > limit:
                raise BudgetExhausted("Monthly AI budget is exhausted")
            request = AiProviderRequest(
                ai_run_id=run_id,
                budget_month=month,
                model=model,
                pricing_version=price.version,
                status="reserved",
                reserved_cost_usd=REQUEST_HOLD_USD,
            )
            session.add(request)
            session.flush()
            return request.id

    def settle(self, request_id: UUID, model: str, input_tokens: int | None, output_tokens: int | None) -> None:
        complete = input_tokens is not None and output_tokens is not None
        cost = (
            estimated_cost(model, input_tokens, output_tokens)
            if input_tokens is not None and output_tokens is not None
            else None
        )
        with self.database.user_transaction(self.actor_id) as session:
            if self.database.engine.dialect.name == "postgresql":
                session.execute(
                    text("SELECT playeriq.ai_budget_settle(:request_id, :model, :inputs, :outputs, :cost)"),
                    {
                        "request_id": request_id,
                        "model": model,
                        "inputs": input_tokens,
                        "outputs": output_tokens,
                        "cost": cost,
                    },
                )
            else:
                request = session.get(AiProviderRequest, request_id)
                if request is None or request.status != "reserved" or request.model != model:
                    raise ValueError("Provider request is not reservable")
                run = session.get(AiRun, request.ai_run_id)
                if run is None or run.actor_user_id != self.actor_id:
                    raise ValueError("Provider request access denied")
                request.status = "completed" if complete else "uncertain"
                request.input_tokens = input_tokens
                request.output_tokens = output_tokens
                request.estimated_cost_usd = cost
                request.completed_at = datetime.now(UTC)

    def uncertain(self, request_id: UUID, model: str) -> None:
        self.settle(request_id, model, None, None)
