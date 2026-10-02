"""Synthetic end-to-end tests for authenticated upload, review and explicit linking."""

from collections.abc import Iterator
from datetime import UTC, datetime
from sqlite3 import OperationalError
from uuid import UUID, uuid4

import pytest
from app.api.errors import AppError
from app.core.auth import CurrentUser
from app.core.config import Settings, get_settings
from app.db.base import Base, auth_users
from app.db.session import Database
from app.main import create_app
from app.models.tables import IngestionJob, PlayerSession, SessionMetricValue, SourceAthleteRow
from app.services.jobs import process_next_job
from conftest import make_synthetic_pdf
from fastapi.testclient import TestClient
from sqlalchemy import Select, create_engine, event, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.pool import StaticPool

OWNER = UUID("00000000-0000-4000-8000-000000000001")
OTHER = UUID("00000000-0000-4000-8000-000000000002")


class FakeVerifier:
    def verify(self, token: str) -> CurrentUser:
        if token == "owner":
            return CurrentUser(OWNER)
        if token == "other":
            return CurrentUser(OTHER)
        raise AppError("invalid_token", "Invalid access token", 401)


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.fail_get = False

    def put(self, key: str, content: bytes) -> None:
        self.objects[key] = content

    def get(self, key: str) -> bytes:
        if self.fail_get:
            raise RuntimeError("synthetic storage failure")
        return self.objects[key]

    def delete(self, key: str) -> None:
        del self.objects[key]


@pytest.fixture
def phase2() -> Iterator[tuple[TestClient, Database, FakeStorage, Settings]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def attach_schemas(dbapi_connection, _record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("ATTACH DATABASE ':memory:' AS auth")
        cursor.execute("ATTACH DATABASE ':memory:' AS playeriq")
        cursor.close()

    Base.metadata.create_all(engine)

    @event.listens_for(engine, "before_execute")
    def reject_read_only_table_row_locks(_conn, statement, _multiparams, _params, _options) -> None:  # type: ignore[no-untyped-def]
        # SQLite omits PostgreSQL locking clauses. Enforce the production role's
        # read-only evidence/player contract throughout synthetic API flows.
        sql = str(statement.compile(dialect=postgresql.dialect()))
        if (
            isinstance(statement, Select)
            and "FOR UPDATE" in sql
            and any(
                getattr(table, "name", None) in ("players", "source_athlete_rows")
                for table in statement.get_final_froms()
            )
        ):
            raise OperationalError("synthetic restricted-role lock permission denied")

    with engine.begin() as connection:
        connection.execute(auth_users.insert(), [{"id": OWNER}, {"id": OTHER}])
    settings = Settings(_env_file=None, supabase_url="https://demo.supabase.co")
    app = create_app(settings)
    database = Database(engine)
    storage = FakeStorage()
    app.state.database = database
    app.state.storage = storage
    app.state.jwt_verifier = FakeVerifier()
    with TestClient(app) as client:
        yield client, database, storage, settings


def _auth(who: str = "owner") -> dict[str, str]:
    return {"Authorization": f"Bearer {who}"}


def _upload(client: TestClient, content: bytes, who: str = "owner") -> dict:
    response = client.post(
        "/v1/report-uploads",
        headers=_auth(who),
        files={"file": ("synthetic.pdf", content, "application/pdf")},
    )
    assert response.status_code == 202, response.text
    return response.json()


def test_job_enqueue_does_not_request_job_columns(
    phase2: tuple[TestClient, Database, FakeStorage, Settings], synthetic_pdf: bytes
) -> None:
    client, database, _, _ = phase2
    job_inserts: list[str] = []

    def observe_job_insert(_conn, _cursor, statement, _parameters, _context, _executemany) -> None:  # type: ignore[no-untyped-def]
        if "INSERT INTO playeriq.ingestion_jobs" in statement:
            job_inserts.append(statement)

    event.listen(database.engine, "before_cursor_execute", observe_job_insert)
    try:
        _upload(client, synthetic_pdf)
    finally:
        event.remove(database.engine, "before_cursor_execute", observe_job_insert)
    assert len(job_inserts) == 1
    assert "RETURNING" not in job_inserts[0].upper()


def test_failed_job_enqueue_rolls_back_upload_and_hides_database_error(
    phase2: tuple[TestClient, Database, FakeStorage, Settings], synthetic_pdf: bytes
) -> None:
    client, database, storage, _ = phase2

    def reject_job_insert(_conn, _cursor, statement, _parameters, _context, _executemany) -> None:  # type: ignore[no-untyped-def]
        if "INSERT INTO playeriq.ingestion_jobs" in statement:
            raise OperationalError("synthetic job enqueue failure")

    event.listen(database.engine, "before_cursor_execute", reject_job_insert)
    try:
        response = client.post(
            "/v1/report-uploads",
            headers=_auth(),
            files={"file": ("synthetic.pdf", synthetic_pdf, "application/pdf")},
        )
    finally:
        event.remove(database.engine, "before_cursor_execute", reject_job_insert)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "upload_processing_failed"
    assert "synthetic job enqueue failure" not in response.text
    assert storage.objects == {}
    assert client.get("/v1/report-uploads", headers=_auth()).json()["items"] == []


def test_uploader_only_upload_history_is_cursor_paginated(
    phase2: tuple[TestClient, Database, FakeStorage, Settings], synthetic_pdf: bytes
) -> None:
    client, _, _, _ = phase2
    first = _upload(client, synthetic_pdf)["upload_id"]
    second = _upload(client, synthetic_pdf + b"\n% second synthetic report")["upload_id"]
    _upload(client, synthetic_pdf, "other")
    assert client.get("/v1/report-uploads").status_code == 401
    page = client.get("/v1/report-uploads?limit=1", headers=_auth())
    assert page.status_code == 200, page.text
    assert len(page.json()["items"]) == 1
    assert page.json()["items"][0]["upload_id"] in {first, second}
    assert page.json()["items"][0]["athlete_row_count"] is None
    next_page = client.get(
        "/v1/report-uploads", headers=_auth(), params={"limit": 1, "cursor": page.json()["next_cursor"]}
    )
    assert next_page.status_code == 200, next_page.text
    assert {page.json()["items"][0]["upload_id"], next_page.json()["items"][0]["upload_id"]} == {first, second}
    assert next_page.json()["next_cursor"] is None
    assert len(client.get("/v1/report-uploads", headers=_auth("other")).json()["items"]) == 1
    assert client.get("/v1/report-uploads?cursor=%%%", headers=_auth()).status_code == 400


def test_authenticated_upload_review_link_and_read(
    phase2: tuple[TestClient, Database, FakeStorage, Settings], synthetic_pdf: bytes
) -> None:
    client, database, storage, settings = phase2
    assert client.get("/v1/me").status_code == 401
    assert client.get("/v1/me", headers=_auth("bad")).status_code == 401
    assert client.get("/v1/me", headers=_auth()).json()["profile"] is None
    assert (
        client.patch(
            "/v1/me", headers=_auth(), json={"display_name": "Test Player", "timezone": "Asia/Riyadh"}
        ).status_code
        == 200
    )
    player = client.post("/v1/players", headers=_auth(), json={"display_name": "Test Player"})
    assert player.status_code == 201, player.text
    player_id = player.json()["id"]
    upload = _upload(client, synthetic_pdf)
    upload_id = upload["upload_id"]
    assert upload["status"] == "queued"
    assert client.get(f"/v1/report-uploads/{upload_id}", headers=_auth("other")).status_code == 404
    assert client.get(f"/v1/report-uploads/{upload_id}/file", headers=_auth("other")).status_code == 404
    assert (
        client.post(
            f"/v1/report-uploads/{upload_id}/links",
            headers=_auth(),
            json={"player_id": player_id, "source_athlete_row_id": str(uuid4())},
        ).status_code
        == 409
    )

    assert process_next_job(database, storage, settings) is True
    assert process_next_job(database, storage, settings) is False
    status = client.get(f"/v1/report-uploads/{upload_id}", headers=_auth())
    assert status.status_code == 200, status.text
    body = status.json()
    assert body["status"] == "awaiting_link"
    assert body["activity"]["activity_total_time_s"] == 5400
    assert len(body["candidate_rows"]) == 12
    assert [row["quality_state"] for row in body["candidate_rows"]].count("zero_recorded") == 2
    assert [row["quality_state"] for row in body["candidate_rows"]].count("needs_review") == 1
    assert any(f["code"] == "chart_only_unavailable" for f in body["findings"])
    assert client.get(f"/v1/players/{player_id}/sessions", headers=_auth()).json()["items"] == []
    zero_row = body["candidate_rows"][1]
    assert "Maximum Velocity" in zero_row["missing_metrics"]
    for index in (1, 8):
        rejected_link = client.post(
            f"/v1/report-uploads/{upload_id}/links",
            headers=_auth(),
            json={"player_id": player_id, "source_athlete_row_id": body["candidate_rows"][index]["id"]},
        )
        assert rejected_link.status_code == 422, rejected_link.text

    row_id = body["candidate_rows"][0]["id"]
    link_request = {"player_id": player_id, "source_athlete_row_id": row_id, "session_type": "training"}
    link = client.post(f"/v1/report-uploads/{upload_id}/links", headers=_auth(), json=link_request)
    assert link.status_code == 200, link.text
    session_id = link.json()["session_id"]
    repeated = client.post(f"/v1/report-uploads/{upload_id}/links", headers=_auth(), json=link_request)
    assert repeated.status_code == 200
    assert repeated.json()["session_id"] == session_id
    assert client.get(f"/v1/players/{player_id}/sessions", headers=_auth("other")).status_code == 404
    sessions = client.get(f"/v1/players/{player_id}/sessions", headers=_auth()).json()
    assert len(sessions["items"]) == 1
    assert sessions["items"][0]["id"] == session_id
    assert client.get(f"/v1/players/{player_id}/sessions?from=2025-03-14", headers=_auth()).json()["items"] == []
    assert client.get(f"/v1/players/{player_id}/sessions?cursor=%%%", headers=_auth()).status_code == 400
    detail = client.get(f"/v1/players/{player_id}/sessions/{session_id}", headers=_auth())
    assert detail.status_code == 200, detail.text
    assert detail.json()["local_date"] == "2025-03-13"
    assert detail.json()["provenance"]["source_athlete_row_id"] == row_id
    assert len(detail.json()["metrics"]) == 8
    assert all(metric["quality_state"] == "accepted" for metric in detail.json()["metrics"])
    assert all(metric["source_label"] != "Averages" for metric in detail.json()["metrics"])
    wrong_row = client.post(f"/v1/report-uploads/{upload_id}/links", headers=_auth("other"), json=link_request)
    assert wrong_row.status_code == 404
    assert client.get(f"/v1/report-uploads/{upload_id}/file", headers=_auth()).content == synthetic_pdf
    with database.worker_transaction() as session:
        saved_session = session.get(PlayerSession, UUID(session_id))
        assert saved_session is not None
        assert saved_session.started_at is None
        assert saved_session.athlete_duration_s is None
        saved_metrics = session.scalars(
            select(SessionMetricValue).where(SessionMetricValue.player_session_id == UUID(session_id))
        ).all()
        assert saved_metrics


def test_upload_validation_duplicate_and_tenant_isolation(
    phase2: tuple[TestClient, Database, FakeStorage, Settings], synthetic_pdf: bytes
) -> None:
    client, _, storage, _ = phase2
    unauthenticated = client.post("/v1/report-uploads", files={"file": ("x.pdf", synthetic_pdf, "application/pdf")})
    assert unauthenticated.status_code == 401
    for filename, mime, content, expected in (
        ("../report.pdf", "application/pdf", synthetic_pdf, 400),
        ("report.txt", "application/pdf", synthetic_pdf, 415),
        ("report.pdf", "text/plain", synthetic_pdf, 415),
        ("report.pdf", "application/pdf", b"not-a-pdf", 415),
        ("report.pdf", "application/pdf", b"%PDF-1.0\nunsupported", 415),
    ):
        response = client.post("/v1/report-uploads", headers=_auth(), files={"file": (filename, content, mime)})
        assert response.status_code == expected, response.text
    first = _upload(client, synthetic_pdf)
    duplicate = client.post(
        "/v1/report-uploads", headers=_auth(), files={"file": ("synthetic.pdf", synthetic_pdf, "application/pdf")}
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "duplicate_upload"
    small_settings = Settings(
        _env_file=None, supabase_url="https://demo.supabase.co", max_upload_bytes=len(synthetic_pdf) - 1
    )
    client.app.dependency_overrides[get_settings] = lambda: small_settings
    oversized = client.post(
        "/v1/report-uploads", headers=_auth(), files={"file": ("synthetic.pdf", synthetic_pdf, "application/pdf")}
    )
    assert oversized.status_code == 413
    client.app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, supabase_url="https://demo.supabase.co"
    )
    second_user = _upload(client, synthetic_pdf, "other")
    assert first["upload_id"] != second_user["upload_id"]
    assert len(storage.objects) == 2


def test_worker_storage_retry_and_no_partial_rows(
    phase2: tuple[TestClient, Database, FakeStorage, Settings], synthetic_pdf: bytes
) -> None:
    client, database, storage, settings = phase2
    upload_id = _upload(client, synthetic_pdf)["upload_id"]
    storage.fail_get = True
    assert process_next_job(database, storage, settings) is True
    status = client.get(f"/v1/report-uploads/{upload_id}", headers=_auth()).json()
    assert status["status"] == "failed_retryable"
    assert status["candidate_rows"] == []
    storage.fail_get = False
    with database.worker_transaction() as session:
        job = session.scalar(select(IngestionJob).where(IngestionJob.upload_id == UUID(upload_id)))
        assert job is not None
        job.next_attempt_at = datetime.now(UTC)
    assert process_next_job(database, storage, settings) is True
    assert client.get(f"/v1/report-uploads/{upload_id}", headers=_auth()).json()["status"] == "awaiting_link"
    with database.worker_transaction() as session:
        job = session.scalar(select(IngestionJob).where(IngestionJob.upload_id == UUID(upload_id)))
        assert job is not None
        job.status = "queued"  # Simulate a replayed job after a worker restart.
        job.next_attempt_at = datetime.now(UTC)
    assert process_next_job(database, storage, settings) is False
    with database.worker_transaction() as session:
        assert len(session.scalars(select(SourceAthleteRow)).all()) == 12


def test_link_authorization_upload_membership_and_conflicts(
    phase2: tuple[TestClient, Database, FakeStorage, Settings], synthetic_pdf: bytes
) -> None:
    client, database, storage, settings = phase2
    owner_player = client.post("/v1/players", headers=_auth(), json={"display_name": "Owner"}).json()["id"]
    other_player = client.post("/v1/players", headers=_auth("other"), json={"display_name": "Other"}).json()["id"]
    first = _upload(client, synthetic_pdf)["upload_id"]
    second = _upload(client, synthetic_pdf + b"\n")["upload_id"]
    assert process_next_job(database, storage, settings)
    assert process_next_job(database, storage, settings)
    first_rows = client.get(f"/v1/report-uploads/{first}", headers=_auth()).json()["candidate_rows"]
    second_rows = client.get(f"/v1/report-uploads/{second}", headers=_auth()).json()["candidate_rows"]

    def link(upload: str, row: str, player: str, who: str = "owner"):
        return client.post(
            f"/v1/report-uploads/{upload}/links",
            headers=_auth(who),
            json={"source_athlete_row_id": row, "player_id": player, "session_type": "training"},
        )

    assert link(first, second_rows[0]["id"], owner_player).status_code == 404
    assert link(first, first_rows[0]["id"], other_player).status_code == 404
    assert link(first, first_rows[0]["id"], owner_player, "other").status_code == 404
    with database.worker_transaction() as session:
        assert session.scalars(select(PlayerSession)).all() == []
    assert link(first, first_rows[0]["id"], owner_player).status_code == 200
    assert link(first, first_rows[2]["id"], owner_player).status_code == 409
    assert link(second, second_rows[0]["id"], owner_player).status_code == 409
    assert client.get(f"/v1/players/{owner_player}/sessions", headers=_auth()).json()["items"][0]["id"]
    assert client.get(f"/v1/players/{other_player}/sessions", headers=_auth("other")).json()["items"] == []


def test_confirmed_source_identity_recognizes_only_exact_active_scope(
    phase2: tuple[TestClient, Database, FakeStorage, Settings], synthetic_pdf: bytes
) -> None:
    client, database, storage, settings = phase2
    client.patch("/v1/me", headers=_auth(), json={"display_name": "ATHLETE1", "timezone": "UTC"})
    player_id = client.post("/v1/players", headers=_auth(), json={"display_name": "ATHLETE1"}).json()["id"]
    first = _upload(client, synthetic_pdf)["upload_id"]
    assert process_next_job(database, storage, settings)
    rows = client.get(f"/v1/report-uploads/{first}", headers=_auth()).json()["candidate_rows"]
    assert rows[0]["recognition_status"] == "unlinked"  # Account name is no proof.
    assert client.get("/v1/me/source-identities", headers=_auth()).json()["items"] == []
    url = f"/v1/report-uploads/{first}/claim-as-self"
    body = {
        "source_athlete_row_id": rows[0]["id"],
        "player_id": player_id,
        "confirmed_source_label": "ATHLETE1",
        "session_type": "training",
    }
    assert client.post(url, headers=_auth("other"), json=body).status_code == 404
    assert client.post(url, headers=_auth(), json={**body, "confirmed_source_label": "OTHER"}).status_code == 409
    assert (
        client.post(
            url,
            headers=_auth(),
            json={**body, "source_athlete_row_id": rows[1]["id"], "confirmed_source_label": "ATHLETE2"},
        ).status_code
        == 422
    )
    claimed = client.post(url, headers=_auth(), json=body)
    assert claimed.status_code == 200, claimed.text
    identity = claimed.json()["identity"]
    assert identity["original_label"] == "ATHLETE1"
    assert identity["confirmed_row_id"] == rows[0]["id"]
    assert identity["status"] == "connected"
    assert client.post(url, headers=_auth(), json=body).json()["session_id"] == claimed.json()["session_id"]

    second_pdf = make_synthetic_pdf("THURSDAY, MARCH 20, 2025", "20250320120000")
    second = _upload(client, second_pdf)["upload_id"]
    assert process_next_job(database, storage, settings)
    future = client.get(f"/v1/report-uploads/{second}", headers=_auth()).json()["candidate_rows"]
    assert future[0]["recognition_status"] == "recognized"
    assert future[0]["recognized_player_id"] == player_id
    assert future[0]["source_identity_id"] == identity["id"]
    assert len(client.get(f"/v1/players/{player_id}/sessions", headers=_auth()).json()["items"]) == 1
    recognized = client.post(
        f"/v1/report-uploads/{second}/links",
        headers=_auth(),
        json={
            "source_athlete_row_id": future[0]["id"],
            "player_id": player_id,
            "session_type": "training",
            "source_identity_id": identity["id"],
        },
    )
    assert recognized.status_code == 200, recognized.text
    assert recognized.json()["link_method"] == "recognized"
    assert len(client.get(f"/v1/players/{player_id}/sessions", headers=_auth()).json()["items"]) == 2
    ambiguous_upload = _upload(client, make_synthetic_pdf("THURSDAY, APRIL 10, 2025", "20250410120000", "ATHLETE3"))[
        "upload_id"
    ]
    assert process_next_job(database, storage, settings)
    ambiguous_rows = client.get(f"/v1/report-uploads/{ambiguous_upload}", headers=_auth()).json()["candidate_rows"]
    ambiguous_claim = client.post(
        f"/v1/report-uploads/{ambiguous_upload}/claim-as-self",
        headers=_auth(),
        json={
            "source_athlete_row_id": ambiguous_rows[0]["id"],
            "player_id": player_id,
            "confirmed_source_label": "ATHLETE3",
            "session_type": "training",
        },
    )
    assert ambiguous_claim.status_code == 409
    assert ambiguous_claim.json()["error"]["code"] == "identity_ambiguous"

    near = _upload(client, make_synthetic_pdf("THURSDAY, MARCH 27, 2025", "20250327120000", "ATHLETE1X"))["upload_id"]
    assert process_next_job(database, storage, settings)
    assert (
        client.get(f"/v1/report-uploads/{near}", headers=_auth()).json()["candidate_rows"][0]["recognition_status"]
        == "unlinked"
    )
    revoked = client.post(f"/v1/me/source-identities/{identity['id']}/revoke", headers=_auth(), json={"confirm": True})
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"
    fourth = _upload(client, make_synthetic_pdf("THURSDAY, APRIL 3, 2025", "20250403120000"))["upload_id"]
    assert process_next_job(database, storage, settings)
    assert (
        client.get(f"/v1/report-uploads/{fourth}", headers=_auth()).json()["candidate_rows"][0]["recognition_status"]
        == "unlinked"
    )
    assert len(client.get(f"/v1/players/{player_id}/sessions", headers=_auth()).json()["items"]) == 2


def test_team_workspace_shares_only_accepted_projections(
    phase2: tuple[TestClient, Database, FakeStorage, Settings], synthetic_pdf: bytes
) -> None:
    client, database, storage, settings = phase2
    for actor, label in (("owner", "Alex Morgan"), ("other", "Jordan Lee")):
        assert (
            client.patch("/v1/me", headers=_auth(actor), json={"display_name": label, "timezone": "UTC"}).status_code
            == 200
        )
    owner_player = client.post("/v1/players", headers=_auth(), json={"display_name": "Alex Morgan"}).json()["id"]
    other_player = client.post("/v1/players", headers=_auth("other"), json={"display_name": "Jordan Lee"}).json()["id"]
    team = client.post("/v1/teams", headers=_auth(), json={"name": "Synthetic FC"})
    assert team.status_code == 201, team.text
    team_id = team.json()["id"]
    assert client.get(f"/v1/teams/{team_id}/dashboard", headers=_auth("other")).status_code == 404
    request = client.post(f"/v1/teams/{team_id}/join-requests", headers=_auth("other"), json={})
    assert request.status_code == 202, request.text
    approved = client.post(
        f"/v1/teams/{team_id}/join-requests/{request.json()['id']}/approve", headers=_auth(), json={"role": "player"}
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["player_id"] == other_player
    assert client.get(f"/v1/teams/{team_id}/dashboard", headers=_auth("other")).status_code == 200
    uploaded = client.post(
        "/v1/report-uploads",
        headers=_auth(),
        data={"team_id": team_id},
        files={"file": ("synthetic.pdf", synthetic_pdf, "application/pdf")},
    )
    assert uploaded.status_code == 202, uploaded.text
    upload_id = uploaded.json()["upload_id"]
    assert process_next_job(database, storage, settings)
    rows = client.get(f"/v1/report-uploads/{upload_id}", headers=_auth()).json()["candidate_rows"]
    linked = client.post(
        f"/v1/report-uploads/{upload_id}/links",
        headers=_auth(),
        json={
            "source_athlete_row_id": rows[0]["id"],
            "player_id": owner_player,
            "session_type": "training",
        },
    )
    assert linked.status_code == 200, linked.text
    teammate_body = {
        "source_athlete_row_id": rows[2]["id"],
        "player_id": other_player,
        "confirmed_source_label": "ATHLETE3",
        "session_type": "training",
    }
    assert (
        client.post(
            f"/v1/report-uploads/{upload_id}/confirm-team-player", headers=_auth("other"), json=teammate_body
        ).status_code
        == 404
    )
    teammate = client.post(f"/v1/report-uploads/{upload_id}/confirm-team-player", headers=_auth(), json=teammate_body)
    assert teammate.status_code == 200, teammate.text
    assert teammate.json()["identity"]["player_id"] == other_player
    assert teammate.json()["identity"]["team_id"] == team_id
    repeat = client.post(f"/v1/report-uploads/{upload_id}/confirm-team-player", headers=_auth(), json=teammate_body)
    assert repeat.status_code == 200
    assert repeat.json()["identity"]["id"] == teammate.json()["identity"]["id"]
    assert (
        client.post(
            f"/v1/report-uploads/{upload_id}/claim-as-self",
            headers=_auth(),
            json={**teammate_body, "player_id": owner_player},
        ).status_code
        == 409
    )
    own_sessions = client.get(f"/v1/players/{owner_player}/sessions", headers=_auth()).json()["items"]
    assert len(own_sessions) == 1
    assert client.get(f"/v1/players/{owner_player}/sessions", headers=_auth("other")).status_code == 404
    assert client.get(f"/v1/report-uploads/{upload_id}", headers=_auth("other")).status_code == 404
    assert client.get(f"/v1/report-uploads/{upload_id}/file", headers=_auth("other")).status_code == 404
    assert client.get(f"/v1/teams/{team_id}/reports", headers=_auth("other")).status_code == 404
    dashboard = client.get(f"/v1/teams/{team_id}/dashboard", headers=_auth()).json()
    assert dashboard["latest_session"]["participant_count"] == 2
    assert dashboard["latest_session"]["report_upload_id"] == upload_id
    assert dashboard["rule_version"] == "analytics_v1"
    detail_url = f"/v1/teams/{team_id}/sessions/{upload_id}"
    assert len(client.get(detail_url, headers=_auth()).json()["participants"]) == 2
    member_detail = client.get(detail_url, headers=_auth("other")).json()
    assert len(member_detail["participants"]) == 1
    assert member_detail["participants"][0]["player_id"] == other_player
    assert "source_name" not in str(member_detail)
    assert len(client.get(f"/v1/teams/{team_id}/players", headers=_auth("other")).json()["items"]) == 1
    assert client.get(f"/v1/teams/{team_id}/players/{owner_player}", headers=_auth("other")).status_code == 404
    assert client.get(f"/v1/teams/{team_id}/players/{other_player}", headers=_auth("other")).status_code == 200
    assert client.get(f"/v1/teams/{team_id}/players/{owner_player}", headers=_auth()).status_code == 200
    next_upload = client.post(
        "/v1/report-uploads",
        headers=_auth(),
        data={"team_id": team_id},
        files={
            "file": (
                "synthetic.pdf",
                make_synthetic_pdf("THURSDAY, MARCH 20, 2025", "20250320120000"),
                "application/pdf",
            )
        },
    )
    assert next_upload.status_code == 202
    assert process_next_job(database, storage, settings)
    next_rows = client.get(f"/v1/report-uploads/{next_upload.json()['upload_id']}", headers=_auth()).json()[
        "candidate_rows"
    ]
    assert next_rows[2]["recognition_status"] == "recognized"
    assert next_rows[2]["recognized_player_id"] == other_player
    assert (
        client.post(
            f"/v1/report-uploads/{next_upload.json()['upload_id']}/confirm-team-player",
            headers=_auth(),
            json={**teammate_body, "source_athlete_row_id": next_rows[2]["id"], "player_id": owner_player},
        ).status_code
        == 409
    )
    second_team = client.post("/v1/teams", headers=_auth(), json={"name": "Different Synthetic FC"}).json()["id"]
    wrong_scope = client.post(
        "/v1/report-uploads",
        headers=_auth(),
        data={"team_id": second_team},
        files={
            "file": (
                "synthetic.pdf",
                make_synthetic_pdf("THURSDAY, MARCH 27, 2025", "20250327120000"),
                "application/pdf",
            )
        },
    )
    assert wrong_scope.status_code == 202
    assert process_next_job(database, storage, settings)
    wrong_rows = client.get(f"/v1/report-uploads/{wrong_scope.json()['upload_id']}", headers=_auth()).json()[
        "candidate_rows"
    ]
    assert wrong_rows[2]["recognition_status"] == "unlinked"


def test_existing_linked_upload_can_join_team_without_inferred_identity(
    phase2: tuple[TestClient, Database, FakeStorage, Settings], synthetic_pdf: bytes
) -> None:
    client, database, storage, settings = phase2
    assert (
        client.patch("/v1/me", headers=_auth(), json={"display_name": "Alex Morgan", "timezone": "UTC"}).status_code
        == 200
    )
    player_id = client.post("/v1/players", headers=_auth(), json={"display_name": "Alex Morgan"}).json()["id"]
    upload_id = _upload(client, synthetic_pdf)["upload_id"]
    assert process_next_job(database, storage, settings)
    row = client.get(f"/v1/report-uploads/{upload_id}", headers=_auth()).json()["candidate_rows"][0]
    linked = client.post(
        f"/v1/report-uploads/{upload_id}/links",
        headers=_auth(),
        json={"source_athlete_row_id": row["id"], "player_id": player_id, "session_type": "training"},
    )
    assert linked.status_code == 200, linked.text
    assert client.get("/v1/me/source-identities", headers=_auth()).json()["items"] == []

    team_id = client.post("/v1/teams", headers=_auth(), json={"name": "Synthetic FC"}).json()["id"]
    assignment = f"/v1/report-uploads/{upload_id}/team"
    assert (
        client.post(assignment, headers=_auth("other"), json={"team_id": team_id, "confirm_share": True}).status_code
        == 404
    )
    assert client.post(assignment, headers=_auth(), json={"team_id": team_id, "confirm_share": True}).status_code == 200
    assert client.post(assignment, headers=_auth(), json={"team_id": team_id, "confirm_share": True}).status_code == 200
    detail = client.get(f"/v1/teams/{team_id}/sessions/{upload_id}", headers=_auth()).json()
    assert detail["summary"]["participant_count"] == 1
    assert detail["participants"][0]["session_id"] == linked.json()["session_id"]
    assert client.get("/v1/me/source-identities", headers=_auth()).json()["items"] == []


def test_chart_review_is_uploader_only_and_updates_linked_history(
    phase2: tuple[TestClient, Database, FakeStorage, Settings], synthetic_pdf: bytes
) -> None:
    client, database, storage, settings = phase2
    player_id = client.post("/v1/players", headers=_auth(), json={"display_name": "Athlete"}).json()["id"]
    upload_id = _upload(client, synthetic_pdf)["upload_id"]
    assert process_next_job(database, storage, settings)
    rows = client.get(f"/v1/report-uploads/{upload_id}", headers=_auth()).json()["candidate_rows"]
    row_id = rows[0]["id"]
    chart_url = f"/v1/report-uploads/{upload_id}/chart-reviews"
    assert client.get(chart_url, headers=_auth("other")).status_code == 404
    assert (
        client.post(
            chart_url,
            headers=_auth("other"),
            json={"source_athlete_row_id": row_id, "metric_key": "player_load_reported", "raw_label": "420"},
        ).status_code
        == 404
    )
    assert (
        client.post(
            chart_url,
            headers=_auth(),
            json={"source_athlete_row_id": rows[1]["id"], "metric_key": "player_load_reported", "raw_label": "0"},
        ).status_code
        == 422
    )

    load_body = {"source_athlete_row_id": row_id, "metric_key": "player_load_reported", "raw_label": "420"}
    load_proposal = client.post(chart_url, headers=_auth(), json=load_body)
    assert load_proposal.status_code == 201, load_proposal.text
    assert load_proposal.json()["status"] == "proposed"
    assert client.post(chart_url, headers=_auth(), json=load_body).json()["id"] == load_proposal.json()["id"]
    confirm_url = f"{chart_url}/{load_proposal.json()['id']}/confirm"
    assert (
        client.post(
            confirm_url, headers=_auth("other"), json={"source_athlete_row_id": row_id, "raw_label": "420"}
        ).status_code
        == 404
    )
    assert (
        client.post(
            confirm_url, headers=_auth(), json={"source_athlete_row_id": row_id, "raw_label": "421"}
        ).status_code
        == 409
    )
    assert (
        client.post(
            confirm_url, headers=_auth(), json={"source_athlete_row_id": rows[2]["id"], "raw_label": "420"}
        ).status_code
        == 409
    )
    confirmed = client.post(confirm_url, headers=_auth(), json={"source_athlete_row_id": row_id, "raw_label": "420"})
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "confirmed"
    assert confirmed.json()["source_observation_id"]

    linked = client.post(
        f"/v1/report-uploads/{upload_id}/links",
        headers=_auth(),
        json={"player_id": player_id, "source_athlete_row_id": row_id, "session_type": "training"},
    )
    assert linked.status_code == 200, linked.text
    session_id = linked.json()["session_id"]
    detail_url = f"/v1/players/{player_id}/sessions/{session_id}"
    detail = client.get(detail_url, headers=_auth()).json()
    assert (
        next(metric for metric in detail["metrics"] if metric["metric_key"] == "player_load_reported")["value"]
        == "420.000"
    )
    overview_url = f"/v1/players/{player_id}/analytics/overview"
    first = client.get(overview_url, headers=_auth())
    assert first.status_code == 200, first.text
    initial_fingerprint = first.json()["history_fingerprint"]
    assert client.get(overview_url, headers=_auth("other")).status_code == 404

    speed_body = {"source_athlete_row_id": row_id, "metric_key": "maximum_velocity_kmh", "raw_label": "29.75"}
    speed = client.post(chart_url, headers=_auth(), json=speed_body).json()
    accepted = client.post(
        f"{chart_url}/{speed['id']}/confirm",
        headers=_auth(),
        json={"source_athlete_row_id": row_id, "raw_label": "29.75"},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "confirmed"
    assert (
        client.post(
            f"{chart_url}/{speed['id']}/confirm",
            headers=_auth(),
            json={"source_athlete_row_id": row_id, "raw_label": "29.75"},
        ).json()["id"]
        == speed["id"]
    )
    updated = client.get(overview_url, headers=_auth()).json()
    assert updated["history_fingerprint"] != initial_fingerprint
    speed_record = next(fact for fact in updated["facts"] if fact["kind"] == "personal_record")
    assert speed_record["value"] == "29.750"
    assert speed_record["rule_version"] == "analytics_v1"

    suspect = client.post(
        chart_url,
        headers=_auth(),
        json={**speed_body, "raw_label": "95.80"},
    ).json()
    held = client.post(
        f"{chart_url}/{suspect['id']}/confirm",
        headers=_auth(),
        json={"source_athlete_row_id": row_id, "raw_label": "95.80"},
    )
    assert held.status_code == 200, held.text
    assert held.json()["status"] == "held"
    assert all(
        metric["metric_key"] != "maximum_velocity_kmh"
        for metric in client.get(detail_url, headers=_auth()).json()["metrics"]
    )
    assert client.get(overview_url, headers=_auth()).json()["history_fingerprint"] != updated["history_fingerprint"]

    corrected = client.post(chart_url, headers=_auth(), json={**speed_body, "raw_label": "30.25"}).json()
    corrected_result = client.post(
        f"{chart_url}/{corrected['id']}/confirm",
        headers=_auth(),
        json={"source_athlete_row_id": row_id, "raw_label": "30.25"},
    )
    assert corrected_result.status_code == 200, corrected_result.text
    assert corrected_result.json()["status"] == "confirmed"
    assert corrected_result.json()["source_observation_id"] != accepted.json()["source_observation_id"]
    assert client.get(overview_url, headers=_auth()).json()["history_fingerprint"] != updated["history_fingerprint"]
    trend_url = f"/v1/players/{player_id}/analytics/trend?metric=maximum_velocity_kmh&from=2025-03-01&to=2025-03-31"
    trend = client.get(trend_url, headers=_auth())
    assert trend.status_code == 200, trend.text
    assert trend.json()["value"] == "30.250"
    assert trend.json()["rule_version"] == "analytics_v1"
    assert client.get(trend_url, headers=_auth("other")).status_code == 404
    assert client.get(f"/v1/players/{player_id}/analytics/outliers", headers=_auth("other")).status_code == 404


def test_worker_persists_automatic_chart_values_and_manual_correction(
    phase2: tuple[TestClient, Database, FakeStorage, Settings], synthetic_text_chart_pdf: bytes
) -> None:
    client, database, storage, settings = phase2
    player_id = client.post("/v1/players", headers=_auth(), json={"display_name": "Synthetic Player"}).json()["id"]
    upload_id = _upload(client, synthetic_text_chart_pdf)["upload_id"]
    assert process_next_job(database, storage, settings)
    assert process_next_job(database, storage, settings) is False
    body = client.get(f"/v1/report-uploads/{upload_id}", headers=_auth()).json()
    assert body["status"] == "awaiting_link"
    assert len(body["candidate_rows"]) == 4
    assert client.get(f"/v1/report-uploads/{upload_id}", headers=_auth("other")).status_code == 404
    first, zero, suspicious, incomplete = body["candidate_rows"]
    assert first["quality_state"] == "ready"
    speed = next(metric for metric in first["metrics"] if metric["source_label"] == "Maximum Velocity")
    load = next(metric for metric in first["metrics"] if metric["source_label"] == "Player Load")
    assert (speed["raw_value"], speed["quality_state"]) == ("29.75", "accepted")
    assert (load["raw_value"], load["quality_state"]) == ("420", "accepted")
    assert "method:pdf_position" in speed["source_locator"]
    assert next(metric for metric in zero["metrics"] if metric["source_label"] == "Player Load")["raw_value"] == "0"
    assert (
        next(metric for metric in suspicious["metrics"] if metric["source_label"] == "Maximum Velocity")[
            "quality_state"
        ]
        == "needs_review"
    )
    assert "Player Load" in incomplete["missing_metrics"]

    link = client.post(
        f"/v1/report-uploads/{upload_id}/links",
        headers=_auth(),
        json={"player_id": player_id, "source_athlete_row_id": first["id"], "session_type": "training"},
    )
    assert link.status_code == 200, link.text
    session_id = link.json()["session_id"]
    detail_url = f"/v1/players/{player_id}/sessions/{session_id}"
    detail = client.get(detail_url, headers=_auth()).json()
    accepted = {metric["metric_key"]: metric for metric in detail["metrics"]}
    assert accepted["maximum_velocity_kmh"]["value"] == "29.750"
    assert accepted["player_load_reported"]["value"] == "420.000"
    overview_url = f"/v1/players/{player_id}/analytics/overview"
    before = client.get(overview_url, headers=_auth()).json()
    assert any(fact["kind"] == "personal_record" and fact["value"] == "29.750" for fact in before["facts"])
    assert all(fact["rule_version"] == "analytics_v1" for fact in before["facts"])
    assert client.get(overview_url, headers=_auth("other")).status_code == 404

    chart_url = f"/v1/report-uploads/{upload_id}/chart-reviews"
    proposal = client.post(
        chart_url,
        headers=_auth(),
        json={"source_athlete_row_id": first["id"], "metric_key": "maximum_velocity_kmh", "raw_label": "30.25"},
    )
    assert proposal.status_code == 201, proposal.text
    assert (
        client.post(
            chart_url,
            headers=_auth("other"),
            json={"source_athlete_row_id": first["id"], "metric_key": "maximum_velocity_kmh", "raw_label": "30.25"},
        ).status_code
        == 404
    )
    confirm = client.post(
        f"{chart_url}/{proposal.json()['id']}/confirm",
        headers=_auth(),
        json={"source_athlete_row_id": first["id"], "raw_label": "30.25"},
    )
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["status"] == "confirmed"
    after = client.get(overview_url, headers=_auth()).json()
    assert after["history_fingerprint"] != before["history_fingerprint"]
    assert (
        next(
            metric
            for metric in client.get(detail_url, headers=_auth()).json()["metrics"]
            if metric["metric_key"] == "maximum_velocity_kmh"
        )["value"]
        == "30.250"
    )
