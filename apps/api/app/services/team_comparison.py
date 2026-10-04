"""Authorize the subject server-side and serialize anonymous peer facts only."""

from decimal import ROUND_HALF_UP, Decimal
from typing import Literal, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.domain import display_decimal
from app.analytics.team_comparison import compare_with_teammates
from app.models.tables import Player, TeamRoster
from app.repositories.team_comparison import report_comparison_history
from app.schemas.teams import MyTeamComparisonOut, PeerComparisonOut
from app.services.authorization import require_team


def _signed_display(value: Decimal | None, unit: str) -> str | None:
    formatted = display_decimal(value, unit)
    return f"+{formatted}" if value is not None and value > 0 else formatted


def my_team_comparison(session: Session, actor_id: UUID, team_id: UUID, report_id: UUID) -> MyTeamComparisonOut:
    _, membership = require_team(session, actor_id, team_id)
    history = report_comparison_history(session, team_id, report_id)
    owned = session.scalar(select(Player).where(Player.owner_user_id == actor_id, Player.archived_at.is_(None)))
    player_id: UUID | None = None
    if owned is not None:
        roster = session.get(TeamRoster, (team_id, owned.id))
        if membership.player_id == owned.id or (
            membership.player_id is None
            and membership.role in ("coach", "admin")
            and roster is not None
            and roster.revoked_at is None
        ):
            player_id = owned.id
    facts = compare_with_teammates(history, team_id, report_id, player_id)
    return MyTeamComparisonOut(
        report_upload_id=report_id,
        status=next((f.status for f in facts if f.status in ("no_player_association", "not_participating")), "ok"),
        metrics=[
            PeerComparisonOut(
                metric_key=f.metric_key,
                status=f.status,
                unit=f.unit,
                your_value=str(f.your_value) if f.your_value is not None else None,
                your_display_value=display_decimal(f.your_value, f.unit),
                teammate_mean=str(f.teammate_mean) if f.teammate_mean is not None else None,
                teammate_display_mean=display_decimal(f.teammate_mean, f.unit),
                absolute_difference=str(f.absolute_difference) if f.absolute_difference is not None else None,
                display_absolute_difference=_signed_display(f.absolute_difference, f.unit),
                percentage_difference=str(f.percentage_difference) if f.percentage_difference is not None else None,
                display_percentage_difference=(
                    format(f.percentage_difference.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP), "+f")
                    if f.percentage_difference is not None
                    else None
                ),
                direction=f.direction,
                teammate_sample_size=f.teammate_sample_size,
                minimum_teammates=cast(Literal[5], f.minimum_teammates),
                rule_version=cast(Literal["analytics_v1"], f.rule_version),
            )
            for f in facts
        ],
    )
