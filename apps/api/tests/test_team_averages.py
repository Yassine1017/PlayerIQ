"""Independent means, same-report scope, metric coverage and authorization."""

from dataclasses import replace
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from app.analytics.domain import MetricValue
from app.analytics.team import TeamMetricSample, same_report_average
from app.services.team_imports import process_next_team_import
from test_phase2_api import _auth
from test_phase2_api import phase2 as existing_phase2
from test_team_imports import team, upload

phase2 = existing_phase2
REPORT = UUID(int=1)


def sample(value: str, key: str = "total_distance_m") -> TeamMetricSample:
    return TeamMetricSample(
        report_id=REPORT,
        player_id=uuid4(),
        session_id=uuid4(),
        session_quality="accepted",
        metric=MetricValue(
            key=key,
            value=Decimal(value),
            unit="m" if key == "total_distance_m" else "source units",
            comparability_key="unverified:same-source",
            definition_id=None,
            source_observation_id=uuid4(),
        ),
    )


def test_distance_mean_uses_accepted_players_not_roster_size_or_other_reports():
    a, b, c = sample("1200"), sample("1800"), sample("6000")
    fact = same_report_average(
        [a, b, replace(c, report_id=uuid4()), replace(c, session_quality="held")], REPORT, "total_distance_m"
    )
    assert fact.value == Decimal("1500") and fact.sample_size == 2
    assert fact.session_ids == (a.session_id, b.session_id)
    assert fact.rule_version == "analytics_v1"


def test_load_mean_includes_accepted_printed_zero_and_excludes_held_values():
    a, b, c = (
        sample("0", "player_load_reported"),
        sample("801", "player_load_reported"),
        sample("999", "player_load_reported"),
    )
    fact = same_report_average(
        [a, b, replace(c, metric=replace(c.metric, quality_state="held"))], REPORT, "player_load_reported"
    )
    assert fact.value == Decimal("400.5") and fact.sample_size == 2
    assert fact.source_observation_ids == (a.metric.source_observation_id, b.metric.source_observation_id)
    assert fact.unit == "source units" and fact.definition_id is None


def test_missing_mean_is_not_zero():
    fact = same_report_average([sample("400")], REPORT, "player_load_reported")
    assert fact.status == "missing_metric" and fact.value is None and fact.sample_size == 0
    assert fact.rule_version == "analytics_v1"


@pytest.mark.parametrize(
    "change",
    [{"unit": "km/h"}, {"definition_id": "other"}, {"comparability_key": "different"}, {"value": Decimal("NaN")}],
)
def test_incompatible_source_values_are_not_averaged(change):
    a, b = sample("300", "player_load_reported"), sample("900", "player_load_reported")
    fact = same_report_average([a, replace(b, metric=replace(b.metric, **change))], REPORT, "player_load_reported")
    assert fact.status == "not_comparable" and fact.value is None


def test_duplicate_player_cannot_inflate_the_mean():
    a, b = sample("1000"), sample("2000")
    fact = same_report_average([a, replace(b, player_id=a.player_id)], REPORT, "total_distance_m")
    assert fact.status == "not_comparable" and fact.value is None


def test_team_api_averages_canonical_chart_values_and_preserves_privacy(phase2, synthetic_text_chart_pdf):
    client, database, storage, settings = phase2
    team_id = team(client)
    upload_id, _ = upload(client, database, storage, settings, team_id, synthetic_text_chart_pdf)
    assert process_next_team_import(database, database, settings)
    response = client.get(f"/v1/teams/{team_id}/dashboard", headers=_auth())
    assert response.status_code == 200
    latest = response.json()["latest_session"]
    assert latest["report_upload_id"] == upload_id
    distance, load = latest["average_distance"], latest["average_player_load"]
    assert Decimal(distance["value"]) == Decimal("3000") and distance["sample_size"] == 3
    assert Decimal(load["value"]) == Decimal("660") and load["sample_size"] == 2
    assert load["comparison_scope"] == "same_report" and load["rule_version"] == "analytics_v1"
    assert len(load["session_ids"]) == len(load["source_observation_ids"]) == 2
    assert client.get(f"/v1/teams/{team_id}/dashboard", headers=_auth("other")).status_code == 404
    join = client.post(f"/v1/teams/{team_id}/join-requests", headers=_auth("other"), json={}).json()
    assert (
        client.post(
            f"/v1/teams/{team_id}/join-requests/{join['id']}/approve", headers=_auth(), json={"role": "player"}
        ).status_code
        == 200
    )
    member = client.get(f"/v1/teams/{team_id}/dashboard", headers=_auth("other")).json()
    assert member["latest_session"]["average_distance"] is None
    assert member["latest_session"]["average_player_load"] is None
    for path in (f"/v1/teams/{team_id}/sessions", f"/v1/teams/{team_id}/sessions/{upload_id}"):
        result = client.get(path, headers=_auth("other")).json()
        summary = result["items"][0] if "items" in result else result["summary"]
        assert summary["average_player_load"] is None
