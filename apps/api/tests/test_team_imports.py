"""Synthetic report import, canonical ownership, recovery and privacy regressions."""

from datetime import date
from uuid import UUID

from app.core.config import Settings
from app.db.session import Database
from app.models.tables import (
    Player,
    PlayerSession,
    PlayerSourceIdentity,
    ReportUpload,
    SessionMetricValue,
    SourceMetricObservation,
    TeamMembership,
    TeamReportImport,
    TeamRosterResolution,
)
from app.services.analytics import AnalyticsService
from app.services.jobs import process_next_job
from app.services.team_imports import process_next_team_import
from conftest import make_synthetic_pdf
from fastapi.testclient import TestClient
from sqlalchemy import event, func, inspect, select
from sqlalchemy.orm import Session
from test_phase2_api import OTHER, OWNER, FakeStorage, _auth
from test_phase2_api import phase2 as existing_phase2

phase2 = existing_phase2


def team(client: TestClient) -> str:
    for who in ("owner", "other"):
        client.patch("/v1/me", headers=_auth(who), json={"display_name": f"Synthetic {who}", "timezone": "UTC"})
        assert (
            client.post("/v1/players", headers=_auth(who), json={"display_name": f"Synthetic {who}"}).status_code == 201
        )
    response = client.post("/v1/teams", headers=_auth(), json={"name": "Synthetic import FC"})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def upload(
    client: TestClient,
    database: Database,
    storage: FakeStorage,
    settings: Settings,
    team_id: str,
    content: bytes,
    automatic: bool = True,
) -> tuple[str, dict]:
    response = client.post(
        "/v1/report-uploads",
        headers=_auth(),
        files={"file": ("synthetic.pdf", content, "application/pdf")},
        data={"team_id": team_id, "import_athletes": str(automatic).lower(), "session_type": "training"},
    )
    assert response.status_code == 202, response.text
    upload_id = response.json()["upload_id"]
    assert process_next_job(database, storage, settings)
    return upload_id, client.get(f"/v1/report-uploads/{upload_id}", headers=_auth()).json()


def status(client: TestClient, upload_id: str) -> dict:
    response = client.get(f"/v1/report-uploads/{upload_id}/team-import", headers=_auth())
    assert response.status_code == 200, response.text
    return response.json()


def request(client: TestClient, upload_id: str, team_id: str, who: str = "owner", session_type: str = "training"):
    return client.post(
        f"/v1/report-uploads/{upload_id}/team-import",
        headers=_auth(who),
        json={"team_id": team_id, "confirm_share": True, "session_type": session_type},
    )


def resolve(client: TestClient, upload_id: str, row: dict, player_id: str | None = None, who: str = "owner"):
    return client.post(
        f"/v1/report-uploads/{upload_id}/team-import/rows/{row['row_id']}/resolve",
        headers=_auth(who),
        json={
            "player_id": player_id or row["player_id"],
            "confirmed_source_label": row["source_name"],
            "confirm_association": True,
        },
    )


def test_more_than_twelve_roster_only_nonparticipants_and_no_auth_permissions(phase2):
    client, database, storage, settings = phase2
    team_id = team(client)
    upload_id, source = upload(client, database, storage, settings, team_id, make_synthetic_pdf(athlete_count=18))
    assert len(source["candidate_rows"]) == 18
    assert status(client, upload_id)["status"] == "queued"
    assert process_next_team_import(database, database, settings)
    result = status(client, upload_id)
    assert result["counts"] == {
        "accepted_session": 15,
        "no_activity": 2,
        "metric_review": 1,
        "total": 18,
        "created_players": 18,
        "created_sessions": 15,
        "accepted_sessions": 15,
    }
    assert result["status"] == "needs_review"
    roster = client.get(f"/v1/teams/{team_id}/players", headers=_auth()).json()["items"]
    assert len(roster) == 19
    assert sum(p["account_state"] == "unclaimed" for p in roster) == 18
    assert sum(p["participation_state"] == "no_accepted_activity" for p in roster) == 4
    no_activity = next(r for r in result["rows"] if r["outcome"] == "no_activity")
    assert no_activity["player_id"] and no_activity["session_id"] is None
    with database.user_transaction(OWNER) as session:
        assert session.scalar(select(func.count()).select_from(TeamMembership)) == 1
        assert session.scalar(select(func.count()).select_from(Player).where(Player.owner_user_id.is_(None))) == 18
        assert session.scalar(select(func.count()).select_from(PlayerSourceIdentity)) == 0
    assert not process_next_team_import(database, database, settings)
    assert request(client, upload_id, team_id).json() == result
    assert client.get(f"/v1/players/{no_activity['player_id']}/analytics/overview", headers=_auth()).status_code == 404


def test_unparsed_source_label_cannot_create_an_athlete(phase2, synthetic_pdf):
    client, database, storage, settings = phase2
    team_id = team(client)
    upload_id, source = upload(client, database, storage, settings, team_id, synthetic_pdf)
    row_id = UUID(source["candidate_rows"][0]["id"])
    with database.worker_transaction() as session:
        observation = session.scalar(
            select(SourceMetricObservation).where(
                SourceMetricObservation.athlete_row_id == row_id,
                SourceMetricObservation.source_label == "Distance (m)",
            )
        )
        assert observation is not None
        observation.raw_value = None
    assert process_next_team_import(database, database, settings)
    result = status(client, upload_id)
    row = next(r for r in result["rows"] if r["row_id"] == str(row_id))
    assert row["player_id"] is None and row["reason_code"] == "source_label_unavailable"
    response = resolve(client, upload_id, row)
    assert response.status_code == 422
    assert status(client, upload_id)["counts"]["created_players"] == 11


def test_confirmed_reuse_and_unconfirmed_name_cannot_merge_history(phase2, synthetic_pdf):
    client, database, storage, settings = phase2
    team_id = team(client)
    upload_id, _ = upload(client, database, storage, settings, team_id, synthetic_pdf)
    assert process_next_team_import(database, database, settings)
    first = status(client, upload_id)["rows"][0]
    assert resolve(client, upload_id, first).status_code == 200
    next_id, _ = upload(
        client, database, storage, settings, team_id, make_synthetic_pdf("FRIDAY, MARCH 14, 2025", "20250314120000")
    )
    assert process_next_team_import(database, database, settings)
    result = status(client, next_id)
    assert result["counts"]["created_players"] == 0
    assert result["rows"][0]["association_method"] == "confirmed_identity"
    assert result["rows"][0]["player_id"] == first["player_id"]
    assert result["rows"][0]["outcome"] == "accepted_session"
    assert result["rows"][2]["reason_code"] == "unconfirmed_source_identity"
    assert result["rows"][2]["session_id"] is None
    assert resolve(client, next_id, result["rows"][2]).status_code == 200
    with database.user_transaction(OWNER) as session:
        history = session.scalars(
            select(PlayerSession).where(PlayerSession.player_id == UUID(first["player_id"]))
        ).all()
        assert {h.local_date for h in history} == {date(2025, 3, 13), date(2025, 3, 14)}


def test_duplicate_labels_require_deliberate_separate_resolution(phase2):
    client, database, storage, settings = phase2
    team_id = team(client)
    upload_id, _ = upload(client, database, storage, settings, team_id, make_synthetic_pdf(first_name="ATHLETE3"))
    assert process_next_team_import(database, database, settings)
    result = status(client, upload_id)
    duplicated = [r for r in result["rows"] if r["source_name"] == "ATHLETE3"]
    assert len(duplicated) == 2
    assert all(r["player_id"] is None and r["reason_code"] == "duplicate_source_label" for r in duplicated)
    for row in duplicated:
        assert resolve(client, upload_id, row).status_code == 200
    results = [r for r in status(client, upload_id)["rows"] if r["source_name"] == "ATHLETE3"]
    assert len({r["player_id"] for r in results}) == 2
    assert all(r["session_id"] for r in results)
    with database.user_transaction(OWNER) as session:
        assert not session.scalars(
            select(PlayerSourceIdentity).where(PlayerSourceIdentity.normalized_label == "athlete3")
        ).all()


def test_explicit_approved_account_association_preserves_canonical_ids_and_fingerprint(phase2, synthetic_pdf):
    client, database, storage, settings = phase2
    team_id = team(client)
    join = client.post(f"/v1/teams/{team_id}/join-requests", headers=_auth("other"), json={}).json()
    assert (
        client.post(
            f"/v1/teams/{team_id}/join-requests/{join['id']}/approve", headers=_auth(), json={"role": "player"}
        ).status_code
        == 200
    )
    other_id = client.get("/v1/players", headers=_auth("other")).json()["items"][0]["id"]
    upload_id, _ = upload(client, database, storage, settings, team_id, synthetic_pdf)
    process_next_team_import(database, database, settings)
    row = status(client, upload_id)["rows"][0]
    candidate = client.get(f"/v1/report-uploads/{upload_id}", headers=_auth()).json()["candidate_rows"][0]
    assert candidate["links"][0]["is_unclaimed"] is True
    before = client.get(f"/v1/players/{other_id}/analytics/overview", headers=_auth("other")).json()[
        "history_fingerprint"
    ]
    with database.user_transaction(OWNER) as session:
        metrics = [
            (m.metric_key, m.source_observation_id, m.value)
            for m in session.scalars(
                select(SessionMetricValue).where(SessionMetricValue.player_session_id == UUID(row["session_id"]))
            ).all()
        ]
    response = resolve(client, upload_id, row, other_id)
    assert response.status_code == 200, response.text
    assert response.json()["rows"][0]["session_id"] == row["session_id"]
    personal = client.get(f"/v1/players/{other_id}/analytics/overview", headers=_auth("other")).json()
    team_view = client.get(f"/v1/teams/{team_id}/players/{other_id}", headers=_auth()).json()
    assert personal["history_fingerprint"] != before
    assert personal["history_fingerprint"] == team_view["history_fingerprint"]
    with database.user_transaction(OWNER) as session:
        assert session.get(Player, UUID(row["player_id"])).owner_user_id is None
        assert session.get(Player, UUID(row["player_id"])).archived_at is not None
        assert session.get(PlayerSession, UUID(row["session_id"])).player_id == UUID(other_id)
        assert [
            (m.metric_key, m.source_observation_id, m.value)
            for m in session.scalars(
                select(SessionMetricValue).where(SessionMetricValue.player_session_id == UUID(row["session_id"]))
            ).all()
        ] == metrics
        assert session.scalar(select(func.count()).select_from(TeamRosterResolution)) == 1
        assert session.scalar(select(func.count()).select_from(TeamMembership)) == 2
    assert resolve(client, upload_id, response.json()["rows"][0], other_id).status_code == 200
    assert client.get(f"/v1/report-uploads/{upload_id}", headers=_auth("other")).status_code == 404
    assert client.get(f"/v1/report-uploads/{upload_id}/team-import", headers=_auth("other")).status_code == 404
    assert client.get(f"/v1/report-uploads/{upload_id}/file", headers=_auth("other")).status_code == 404


def test_cross_team_scope_and_denied_assignment_import_resolution(phase2, synthetic_pdf):
    client, database, storage, settings = phase2
    first_team = team(client)
    upload_id, _ = upload(client, database, storage, settings, first_team, synthetic_pdf)
    process_next_team_import(database, database, settings)
    row = status(client, upload_id)["rows"][0]
    second_team = client.post("/v1/teams", headers=_auth(), json={"name": "Second Synthetic FC"}).json()["id"]
    assert request(client, upload_id, second_team).status_code == 409
    assert request(client, upload_id, first_team, "other").status_code == 404
    assert resolve(client, upload_id, row, who="other").status_code == 404
    assert client.get(f"/v1/teams/{second_team}/players/{row['player_id']}", headers=_auth()).status_code == 404
    another_id, _ = upload(
        client, database, storage, settings, second_team, make_synthetic_pdf("FRIDAY, MARCH 14, 2025", "20250314120000")
    )
    process_next_team_import(database, database, settings)
    assert status(client, another_id)["rows"][0]["player_id"] != row["player_id"]


def test_failure_retry_is_atomic_and_rechecks_membership(phase2, synthetic_pdf, monkeypatch):
    client, database, storage, settings = phase2
    team_id = team(client)
    upload_id, _ = upload(client, database, storage, settings, team_id, synthetic_pdf)
    import app.services.team_imports as imports

    real_link = imports.link_athlete_row
    calls = 0

    def failing(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise RuntimeError("synthetic failure")
        return real_link(*args, **kwargs)

    monkeypatch.setattr(imports, "link_athlete_row", failing)
    for _ in range(3):
        assert process_next_team_import(database, database, settings)
    failed = status(client, upload_id)
    assert failed["status"] == "failed" and failed["attempts"] == 3
    assert failed["rows"] == []
    with database.user_transaction(OWNER) as session:
        assert session.scalar(select(func.count()).select_from(PlayerSession)) == 0
        assert session.scalar(select(func.count()).select_from(Player).where(Player.owner_user_id.is_(None))) == 0
    monkeypatch.setattr(imports, "link_athlete_row", real_link)
    assert request(client, upload_id, team_id).json()["status"] == "queued"
    assert process_next_team_import(database, database, settings)
    assert status(client, upload_id)["counts"]["created_players"] == 12


def test_existing_private_upload_preserves_link_and_manual_chart_values(phase2, synthetic_pdf):
    client, database, storage, settings = phase2
    team_id = team(client)
    response = client.post(
        "/v1/report-uploads", headers=_auth(), files={"file": ("synthetic.pdf", synthetic_pdf, "application/pdf")}
    ).json()
    upload_id = response["upload_id"]
    process_next_job(database, storage, settings)
    source = client.get(f"/v1/report-uploads/{upload_id}", headers=_auth()).json()
    chart_url = f"/v1/report-uploads/{upload_id}/chart-reviews"
    row_id = source["candidate_rows"][0]["id"]
    for key, label in (("player_load_reported", "425"), ("maximum_velocity_kmh", "95.80")):
        proposal = client.post(
            chart_url, headers=_auth(), json={"source_athlete_row_id": row_id, "metric_key": key, "raw_label": label}
        ).json()
        assert (
            client.post(
                f"{chart_url}/{proposal['id']}/confirm",
                headers=_auth(),
                json={"source_athlete_row_id": row_id, "raw_label": label},
            ).status_code
            == 200
        )
    own_id = client.get("/v1/players", headers=_auth()).json()["items"][0]["id"]
    linked = client.post(
        f"/v1/report-uploads/{upload_id}/links",
        headers=_auth(),
        json={
            "source_athlete_row_id": source["candidate_rows"][0]["id"],
            "player_id": own_id,
            "session_type": "training",
        },
    )
    assert linked.status_code == 200, linked.text

    def assert_persisted_source_team(session, _flush_context, _instances):
        for item in session.dirty:
            if isinstance(item, PlayerSession) and inspect(item).attrs.team_id.history.has_changes():
                persisted_team = session.connection().scalar(
                    select(ReportUpload.team_id).where(ReportUpload.id == UUID(upload_id))
                )
                assert persisted_team == UUID(team_id)

    event.listen(Session, "before_flush", assert_persisted_source_team)
    try:
        assert request(client, upload_id, team_id).status_code == 202
    finally:
        event.remove(Session, "before_flush", assert_persisted_source_team)
    process_next_team_import(database, database, settings)
    result = status(client, upload_id)
    assert result["rows"][0]["session_id"] == linked.json()["session_id"]
    assert result["rows"][0]["association_method"] == "existing_link"
    assert result["counts"]["created_players"] == 11
    with database.user_transaction(OWNER) as session:
        metrics = {
            m.metric_key: m.value
            for m in session.scalars(
                select(SessionMetricValue).where(
                    SessionMetricValue.player_session_id == UUID(linked.json()["session_id"])
                )
            ).all()
        }
        assert str(metrics["player_load_reported"]) == "425.000"
        assert "maximum_velocity_kmh" not in metrics
    assert request(client, upload_id, team_id, session_type="match").status_code == 409


def test_this_is_me_can_deliberately_connect_own_imported_row(phase2, synthetic_pdf):
    client, database, storage, settings = phase2
    team_id = team(client)
    upload_id, _ = upload(client, database, storage, settings, team_id, synthetic_pdf)
    process_next_team_import(database, database, settings)
    row = status(client, upload_id)["rows"][0]
    own_id = client.get("/v1/players", headers=_auth()).json()["items"][0]["id"]
    response = client.post(
        f"/v1/report-uploads/{upload_id}/claim-as-self",
        headers=_auth(),
        json={
            "source_athlete_row_id": row["row_id"],
            "player_id": own_id,
            "confirmed_source_label": row["source_name"],
            "session_type": "training",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["session_id"] == row["session_id"]
    assert response.json()["identity"]["player_id"] == own_id
    candidate = client.get(f"/v1/report-uploads/{upload_id}", headers=_auth()).json()["candidate_rows"][0]
    assert candidate["links"][0]["is_unclaimed"] is False


def test_conflicting_mapping_is_visible_review_and_does_not_fail_other_rows(phase2, synthetic_pdf):
    client, database, storage, settings = phase2
    team_id = team(client)
    upload_id, _ = upload(client, database, storage, settings, team_id, synthetic_pdf)
    process_next_team_import(database, database, settings)
    first = status(client, upload_id)["rows"][0]
    assert resolve(client, upload_id, first).status_code == 200
    with database.user_transaction(OWNER) as session:
        mapping = session.scalar(
            select(PlayerSourceIdentity).where(PlayerSourceIdentity.player_id == UUID(first["player_id"]))
        )
        other_id = session.scalar(select(Player.id).where(Player.owner_user_id == OTHER))
        mapping.player_id = other_id  # Fabricated inconsistent scoped evidence, never used in live checks.
    next_id, _ = upload(
        client, database, storage, settings, team_id, make_synthetic_pdf("FRIDAY, MARCH 14, 2025", "20250314120000")
    )
    process_next_team_import(database, database, settings)
    result = status(client, next_id)
    assert result["status"] == "needs_review"
    assert result["rows"][0]["reason_code"] == "identity_conflict"
    assert result["rows"][0]["session_id"] is None


def test_import_rechecks_revoked_manager_authorization(phase2, synthetic_pdf):
    from datetime import UTC, datetime

    client, database, storage, settings = phase2
    team_id = team(client)
    upload_id, _ = upload(client, database, storage, settings, team_id, synthetic_pdf)
    with database.user_transaction(OWNER) as session:
        session.get(TeamMembership, (UUID(team_id), OWNER)).revoked_at = datetime.now(UTC)
    process_next_team_import(database, database, settings)
    with database.user_transaction(OWNER) as session:
        assert session.get(TeamReportImport, UUID(upload_id)).error_code == "team_not_found"
        assert session.scalar(select(func.count()).select_from(PlayerSession)) == 0


def test_same_date_conflict_does_not_overwrite_and_history_is_stale(phase2, synthetic_pdf):
    client, database, storage, settings = phase2
    team_id = team(client)
    first_id, _ = upload(client, database, storage, settings, team_id, synthetic_pdf)
    process_next_team_import(database, database, settings)
    row = status(client, first_id)["rows"][0]
    assert resolve(client, first_id, row).status_code == 200
    next_id, _ = upload(client, database, storage, settings, team_id, make_synthetic_pdf(activity_id="20250313123000"))
    process_next_team_import(database, database, settings)
    result = status(client, next_id)["rows"][0]
    assert result["outcome"] == "session_conflict" and result["reason_code"] == "same_date_review"
    with database.user_transaction(OWNER) as session:
        assert len(AnalyticsService(session, UUID(row["player_id"])).history) == 1
