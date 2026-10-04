"""Independent peer arithmetic, anonymity and canonical correction regressions."""

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from app.analytics.domain import MetricValue, SessionValue
from app.analytics.team_comparison import (
    COMPARISON_METRICS,
    TeamSessionValue,
    compare_with_teammates,
    comparison_fingerprint,
    comparison_unit,
)
from app.api.errors import AppError
from app.models.tables import Player, PlayerSession, SessionMetricValue, TeamMembership
from app.repositories.team_comparison import report_comparison_history
from app.services.team_imports import process_next_team_import
from sqlalchemy import select
from test_phase2_api import OTHER, OWNER, _auth
from test_phase2_api import phase2 as existing_phase2
from test_team_imports import team, upload

phase2 = existing_phase2
TEAM, REPORT, SELF = UUID(int=1), UUID(int=2), UUID(int=3)


def sample(value: str, player: UUID | None = None) -> TeamSessionValue:
    metrics = {
        key: MetricValue(key, Decimal(value), comparison_unit(key), "unverified:same-report", None, uuid4())
        for key in COMPARISON_METRICS
    }
    return TeamSessionValue(
        TEAM, REPORT, player or uuid4(), SessionValue(uuid4(), date(2026, 1, 1), None, "training", "accepted", metrics)
    )


def cohort():
    return [sample("3500", SELF), *(sample(v) for v in ("2000", "2500", "3000", "3500", "4000"))]


def mutate_metric(item, key="total_distance_m", **kwargs):
    return replace(
        item,
        session=replace(
            item.session, metrics={**item.session.metrics, key: replace(item.session.metrics[key], **kwargs)}
        ),
    )


def test_independent_mean_excludes_self_and_keeps_rule_and_internal_evidence():
    history = cohort()
    fact = compare_with_teammates(history, TEAM, REPORT, SELF)[0]
    assert fact.your_value == 3500 and fact.teammate_mean == 3000
    assert fact.absolute_difference == 500
    assert fact.percentage_difference.quantize(Decimal("0.0001")) == Decimal("16.6667")
    assert fact.teammate_sample_size == 5 and fact.minimum_teammates == 5
    assert fact.direction == "above" and fact.rule_version == "analytics_v1"
    assert len(fact.supporting_session_ids) == len(fact.supporting_observation_ids) == 6


@pytest.mark.parametrize("peer_count", [0, 1, 4])
def test_small_cohorts_suppress_all_benchmark_values(peer_count):
    facts = compare_with_teammates(cohort()[: peer_count + 1], TEAM, REPORT, SELF)
    assert all(f.status == "insufficient_cohort" and f.teammate_sample_size == peer_count for f in facts)
    assert all(
        f.teammate_mean is None
        and f.absolute_difference is None
        and f.percentage_difference is None
        and f.direction is None
        and not f.supporting_session_ids
        for f in facts
    )


@pytest.mark.parametrize(
    "your,peer,delta,percent,direction",
    [
        ("0", "0", "0", None, "equal"),
        ("50", "0", "50", None, "above"),
        ("100", "100", "0", "0", "equal"),
        ("50", "100", "-50", "-50", "below"),
    ],
)
def test_zeros_equal_and_negative_differences(your, peer, delta, percent, direction):
    history = [sample(your, SELF), *(sample(peer) for _ in range(5))]
    fact = compare_with_teammates(history, TEAM, REPORT, SELF)[0]
    assert fact.status == "ok" and fact.absolute_difference == Decimal(delta)
    assert fact.percentage_difference == (Decimal(percent) if percent is not None else None)
    assert fact.direction == direction


@pytest.mark.parametrize("quality", ["held", "proposed", "missing", "anomalous"])
def test_metric_quality_affects_only_its_own_cohort(quality):
    history = cohort()
    history[-1] = mutate_metric(history[-1], quality_state=quality)
    facts = compare_with_teammates(history, TEAM, REPORT, SELF)
    assert facts[0].status == "insufficient_cohort" and facts[0].teammate_sample_size == 4
    assert all(f.status == "ok" for f in facts[1:])
    history[0] = mutate_metric(history[0], quality_state=quality)
    assert compare_with_teammates(history, TEAM, REPORT, SELF)[0].status == "missing_metric"


@pytest.mark.parametrize("change", ["team", "report", "match", "held", "zero_recorded"])
def test_out_of_scope_or_unaccepted_sessions_do_not_change_cohort(change):
    history = cohort()
    extra = sample("999999")
    extra = (
        replace(extra, team_id=uuid4())
        if change == "team"
        else (
            replace(extra, report_id=uuid4())
            if change == "report"
            else replace(
                extra,
                session=replace(extra.session, session_type="match")
                if change == "match"
                else replace(extra.session, quality_state=change),
            )
        )
    )
    fact = compare_with_teammates(history + [extra], TEAM, REPORT, SELF)[0]
    assert fact.teammate_sample_size == 5 and fact.teammate_mean == 3000


@pytest.mark.parametrize(
    "changes",
    [
        {"unit": "km"},
        {"definition_id": "different"},
        {"comparability_key": "different"},
        {"value": Decimal("NaN")},
        {"value": Decimal("-1")},
    ],
)
def test_incompatible_values_fail_closed_without_cherry_picking(changes):
    history = cohort()
    history[-1] = mutate_metric(history[-1], **changes)
    fact = compare_with_teammates(history, TEAM, REPORT, SELF)[0]
    assert fact.status == "not_comparable" and fact.teammate_mean is None


def test_duplicate_participant_or_observation_fails_closed():
    history = cohort()
    assert compare_with_teammates(history + [history[-1]], TEAM, REPORT, SELF)[0].status == "not_comparable"
    assert all(f.status == "not_comparable" for f in compare_with_teammates(history + [history[0]], TEAM, REPORT, SELF))
    history[-1] = mutate_metric(
        history[-1], source_observation_id=history[0].session.metrics["total_distance_m"].source_observation_id
    )
    assert compare_with_teammates(history, TEAM, REPORT, SELF)[0].status == "not_comparable"


def test_missing_association_participation_and_metric_are_explicit():
    history = cohort()
    assert all(f.status == "no_player_association" for f in compare_with_teammates(history, TEAM, REPORT, None))
    assert all(f.status == "not_participating" for f in compare_with_teammates(history, TEAM, REPORT, uuid4()))
    history[0] = replace(history[0], session=replace(history[0].session, metrics={}))
    assert all(f.status == "missing_metric" for f in compare_with_teammates(history, TEAM, REPORT, SELF))


def test_unknown_types_only_compare_to_unknown_and_load_is_same_report():
    history = [replace(item, session=replace(item.session, session_type="unknown")) for item in cohort()]
    facts = compare_with_teammates(history, TEAM, REPORT, SELF)
    assert facts[-1].status == "ok" and facts[-1].unit == "source units"
    history[-1] = replace(history[-1], report_id=uuid4())
    assert compare_with_teammates(history, TEAM, REPORT, SELF)[-1].status == "insufficient_cohort"


def test_fingerprint_covers_peer_corrections_quality_scope_association_and_rule(monkeypatch):
    history = cohort()
    original = comparison_fingerprint(history, TEAM, REPORT, SELF)
    assert comparison_fingerprint(list(reversed(history)), TEAM, REPORT, SELF) == original
    for changed in [
        mutate_metric(history[-1], value=Decimal("4100")),
        mutate_metric(history[-1], quality_state="held"),
        mutate_metric(history[-1], source_observation_id=uuid4()),
        mutate_metric(history[-1], comparability_key="changed"),
        replace(history[-1], player_id=uuid4()),
        replace(history[-1], team_id=uuid4()),
        replace(history[-1], session=replace(history[-1].session, session_type="match")),
    ]:
        assert comparison_fingerprint([*history[:-1], changed], TEAM, REPORT, SELF) != original
    assert comparison_fingerprint(history, TEAM, REPORT, None) != original
    monkeypatch.setattr("app.analytics.team_comparison.MINIMUM_TEAMMATES", 6)
    assert comparison_fingerprint(history, TEAM, REPORT, SELF) != original
    monkeypatch.setattr("app.analytics.team_comparison.MINIMUM_TEAMMATES", 5)
    monkeypatch.setattr("app.analytics.team_comparison.ANALYTICS_RULE_VERSION", "synthetic-rule-change")
    assert comparison_fingerprint(history, TEAM, REPORT, SELF) != original


@pytest.fixture
def comparison_api(phase2, synthetic_pdf):
    client, database, storage, settings = phase2
    team_id = team(client)
    report_id, reviewed = upload(client, database, storage, settings, team_id, synthetic_pdf)
    assert process_next_team_import(database, database, settings)
    row = reviewed["candidate_rows"][0]
    owned = client.get("/v1/players", headers=_auth()).json()["items"][0]["id"]
    claim = client.post(
        f"/v1/report-uploads/{report_id}/claim-as-self",
        headers=_auth(),
        json={
            "source_athlete_row_id": row["id"],
            "player_id": owned,
            "confirmed_source_label": row["source_name"],
            "session_type": "training",
        },
    )
    assert claim.status_code == 200, claim.text
    with database.user_transaction(OWNER) as session:
        rows = list(
            session.scalars(
                select(PlayerSession)
                .where(PlayerSession.report_upload_id == UUID(report_id))
                .order_by(PlayerSession.id)
            )
        )
        rows.sort(key=lambda item: item.player_id != UUID(owned))
        active = rows[:6]
        for item in rows[6:]:
            item.quality_state = "held"
        for item, value in zip(active, [3500, 2000, 2500, 3000, 3500, 4000], strict=True):
            session.get(SessionMetricValue, (item.id, "total_distance_m")).value = Decimal(value)
        active_ids = [item.id for item in active]
        source_ids = [item.source_athlete_row_id for item in active]
    # Exercise real synthetic uploader review to add canonical chart values.
    for row_id in source_ids:
        review = client.post(
            f"/v1/report-uploads/{report_id}/chart-reviews",
            headers=_auth(),
            json={
                "source_athlete_row_id": str(row_id),
                "metric_key": "maximum_velocity_kmh",
                "raw_label": "30.0",
            },
        )
        assert review.status_code == 201, review.text
        confirmed = client.post(
            f"/v1/report-uploads/{report_id}/chart-reviews/{review.json()['id']}/confirm",
            headers=_auth(),
            json={"source_athlete_row_id": str(row_id), "raw_label": "30.0"},
        )
        assert confirmed.status_code == 200, confirmed.text
    return client, database, team_id, report_id, owned, active_ids, source_ids


def url(data):
    return f"/v1/teams/{data[2]}/sessions/{data[3]}/my-comparison"


def test_api_grounded_mean_anonymous_contract_and_no_cache(comparison_api):
    client, database, _, report_id, _, ids, source_ids = comparison_api
    response = client.get(url(comparison_api), headers=_auth())
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "private, no-store"
    payload = response.json()
    assert payload["report_upload_id"] == report_id and payload["rule_version"] == "analytics_v1"
    fact = payload["metrics"][0]
    assert fact["status"] == "ok" and Decimal(fact["teammate_mean"]) == 3000
    assert fact["display_absolute_difference"] == "+500" and fact["display_percentage_difference"] == "+16.6667"
    assert fact["teammate_sample_size"] == 5 and fact["minimum_teammates"] == 5
    serialized = str(payload)
    assert all(str(value) not in serialized for value in ids + source_ids)
    assert not any(
        key in serialized for key in ("ATHLETE", "player_id", "source_observation", "fingerprint", "session_ids")
    )
    with database.user_transaction(OWNER) as session:
        for item in session.scalars(select(Player)):
            assert str(item.id) not in serialized


def test_api_metric_specific_cohort_suppression_and_no_zero_substitution(comparison_api):
    client, database, _, _, _, ids, _ = comparison_api
    with database.user_transaction(OWNER) as session:
        session.get(SessionMetricValue, (ids[-1], "total_distance_m")).quality_state = "held"
    facts = client.get(url(comparison_api), headers=_auth()).json()["metrics"]
    assert facts[0]["status"] == "insufficient_cohort" and facts[0]["teammate_sample_size"] == 4
    assert facts[0]["your_value"] is not None and facts[0]["teammate_mean"] is None
    assert facts[2]["status"] == "ok"


def test_api_correction_changes_peer_mean_and_internal_fingerprint(comparison_api):
    client, database, team_id, report_id, owned, _, source_ids = comparison_api
    with database.user_transaction(OWNER) as session:
        before = comparison_fingerprint(
            report_comparison_history(session, UUID(team_id), UUID(report_id)),
            UUID(team_id),
            UUID(report_id),
            UUID(owned),
        )
    old = client.get(url(comparison_api), headers=_auth()).json()["metrics"][2]
    assert Decimal(old["teammate_mean"]) == 30
    review = client.post(
        f"/v1/report-uploads/{report_id}/chart-reviews",
        headers=_auth(),
        json={
            "source_athlete_row_id": str(source_ids[-1]),
            "metric_key": "maximum_velocity_kmh",
            "raw_label": "32.0",
        },
    ).json()
    assert (
        client.post(
            f"/v1/report-uploads/{report_id}/chart-reviews/{review['id']}/confirm",
            headers=_auth(),
            json={"source_athlete_row_id": str(source_ids[-1]), "raw_label": "32.0"},
        ).status_code
        == 200
    )
    updated = client.get(url(comparison_api), headers=_auth()).json()["metrics"][2]
    assert Decimal(updated["teammate_mean"]) == Decimal("30.4") and updated["direction"] == "below"
    with database.user_transaction(OWNER) as session:
        assert (
            comparison_fingerprint(
                report_comparison_history(session, UUID(team_id), UUID(report_id)),
                UUID(team_id),
                UUID(report_id),
                UUID(owned),
            )
            != before
        )


@pytest.mark.parametrize("query", ["player_id=other", "metric=total_distance_m", "type=match", "limit=1"])
def test_api_rejects_subject_switch_and_cohort_filters(comparison_api, query):
    assert comparison_api[0].get(f"{url(comparison_api)}?{query}", headers=_auth()).status_code == 422


def test_api_membership_ownership_and_report_boundaries(comparison_api):
    client, database, team_id, report_id, _, ids, _ = comparison_api
    assert client.get(url(comparison_api)).status_code == 401
    assert client.get(url(comparison_api), headers=_auth("other")).status_code == 404
    join = client.post(f"/v1/teams/{team_id}/join-requests", headers=_auth("other"), json={}).json()
    assert client.get(url(comparison_api), headers=_auth("other")).status_code == 404
    client.post(f"/v1/teams/{team_id}/join-requests/{join['id']}/approve", headers=_auth(), json={"role": "player"})
    not_participating = client.get(url(comparison_api), headers=_auth("other")).json()
    assert not_participating["status"] == "not_participating"
    with database.user_transaction(OWNER) as session:
        membership = session.get(TeamMembership, (UUID(team_id), OTHER))
        membership.player_id = session.get(
            PlayerSession, ids[0]
        ).player_id  # mismatched ownership must never switch subject
    assert client.get(url(comparison_api), headers=_auth("other")).json()["status"] == "no_player_association"
    assert client.get(f"/v1/teams/{team_id}/sessions/{uuid4()}/my-comparison", headers=_auth()).status_code == 404
    assert client.get(f"/v1/teams/{uuid4()}/sessions/{report_id}/my-comparison", headers=_auth()).status_code == 404
    with database.user_transaction(OWNER) as session:
        session.get(TeamMembership, (UUID(team_id), OTHER)).revoked_at = datetime.now(UTC)
    assert client.get(url(comparison_api), headers=_auth("other")).status_code == 404


def test_api_player_comparison_preserves_private_team_and_personal_access(comparison_api):
    client, database, team_id, report_id, owned, ids, _ = comparison_api
    join = client.post(f"/v1/teams/{team_id}/join-requests", headers=_auth("other"), json={}).json()
    client.post(f"/v1/teams/{team_id}/join-requests/{join['id']}/approve", headers=_auth(), json={"role": "player"})
    with database.user_transaction(OWNER) as session:
        other_id = session.scalar(select(Player.id).where(Player.owner_user_id == OTHER))
        session.get(PlayerSession, ids[-1]).player_id = other_id
    payload = client.get(url(comparison_api), headers=_auth("other")).json()
    assert payload["metrics"][0]["status"] == "ok" and Decimal(payload["metrics"][0]["your_value"]) == 4000
    assert all(key not in str(payload) for key in ("source_observation", "player_id", "ATHLETE"))
    assert client.get(f"/v1/teams/{team_id}/players/{owned}", headers=_auth("other")).status_code == 404
    assert client.get(f"/v1/players/{owned}/sessions", headers=_auth("other")).status_code == 404
    assert client.get(f"/v1/players/{owned}/chats", headers=_auth("other")).status_code == 404
    for suffix in ("", "/file", "/chart-reviews", "/team-import"):
        assert client.get(f"/v1/report-uploads/{report_id}{suffix}", headers=_auth("other")).status_code == 404
    detail = client.get(f"/v1/teams/{team_id}/sessions/{report_id}", headers=_auth("other")).json()
    assert len(detail["participants"]) == 1
    assert detail["summary"]["average_distance"] is None


def test_manager_role_alone_does_not_invent_player_association(comparison_api):
    client, _, team_id, _, _, _, _ = comparison_api
    join = client.post(f"/v1/teams/{team_id}/join-requests", headers=_auth("other"), json={}).json()
    assert (
        client.post(
            f"/v1/teams/{team_id}/join-requests/{join['id']}/approve", headers=_auth(), json={"role": "coach"}
        ).status_code
        == 200
    )
    payload = client.get(url(comparison_api), headers=_auth("other")).json()
    assert payload["status"] == "no_player_association"
    assert all(f["your_value"] is None and f["teammate_mean"] is None for f in payload["metrics"])


def test_repository_bound_is_enforced_before_metric_query():
    session = MagicMock()
    session.scalars.return_value = [object()] * 201
    with pytest.raises(AppError) as caught:
        report_comparison_history(session, TEAM, REPORT)
    assert caught.value.code == "team_comparison_limit"
    assert session.scalars.call_count == 1
