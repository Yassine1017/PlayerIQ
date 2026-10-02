"""Opt-in development checks; synthetic team writes are always rolled back."""

import os
from uuid import UUID, uuid4

import pytest
from app.api.errors import AppError
from app.core.config import get_settings
from app.db.session import Database, make_engine
from app.models.tables import (
    Player,
    PlayerSession,
    ReportUpload,
    SourceAthleteRow,
    Team,
    TeamManagerGrant,
    TeamMembership,
    TeamRoster,
)
from app.schemas.team_imports import ImportResolution, TeamImportRequest
from app.services.team_imports import execute_import, import_out, request_import, resolve_row
from app.services.teams import create_team, list_teams, team_dashboard
from app.services.transaction_locks import lock_resource
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError


def test_development_supabase_role_migration_and_rls() -> None:
    if os.getenv("PLAYERIQ_LIVE_TEST") != "development":
        pytest.skip("Set PLAYERIQ_LIVE_TEST=development for read-only development checks")
    url = os.getenv("PLAYERIQ_TEST_DATABASE_URL")
    project_ref = os.getenv("PLAYERIQ_TEST_PROJECT_REF")
    if not url or not project_ref or len(project_ref) < 10 or project_ref not in url:
        pytest.fail("A project-matched development test URL and project reference are required")
    engine = make_engine(url)
    database = Database(engine)
    try:
        database.check_connection()
        with engine.connect() as connection:
            tables = connection.execute(
                text(
                    "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity "
                    "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = 'playeriq' AND c.relname IN "
                    "('report_uploads', 'ingestion_jobs', 'source_athlete_rows', 'player_sessions', "
                    "'session_metric_values', 'chart_metric_reviews')"
                )
            ).all()
            assert len(tables) == 6
            assert all(row[1] and row[2] for row in tables)
            job_access = connection.execute(
                text(
                    "SELECT has_table_privilege(current_user, 'playeriq.ingestion_jobs', 'INSERT'), "
                    "has_table_privilege(current_user, 'playeriq.ingestion_jobs', 'SELECT'), "
                    "has_table_privilege(current_user, 'playeriq.ingestion_jobs', 'UPDATE'), "
                    "has_table_privilege(current_user, 'playeriq.ingestion_jobs', 'DELETE'), "
                    "has_table_privilege('playeriq_worker', 'playeriq.ingestion_jobs', 'SELECT'), "
                    "has_table_privilege('playeriq_worker', 'playeriq.ingestion_jobs', 'UPDATE'), "
                    "has_table_privilege('anon', 'playeriq.ingestion_jobs', 'INSERT'), "
                    "has_table_privilege('authenticated', 'playeriq.ingestion_jobs', 'INSERT')"
                )
            ).one()
            assert tuple(job_access) == (True, False, False, False, True, True, False, False)
            job_policies = connection.scalar(
                text(
                    "SELECT count(*) FROM pg_policies WHERE schemaname = 'playeriq' "
                    "AND tablename = 'ingestion_jobs' AND policyname IN "
                    "('ingestion_jobs_owner_insert', 'ingestion_jobs_worker_all')"
                )
            )
            assert job_policies == 2
            policy_count = connection.scalar(
                text(
                    "SELECT count(*) FROM pg_policies WHERE schemaname = 'playeriq' "
                    "AND policyname = 'player_sessions_access_insert'"
                )
            )
            assert policy_count == 1
            review_policies = connection.scalar(
                text(
                    "SELECT count(*) FROM pg_policies WHERE schemaname = 'playeriq' "
                    "AND tablename = 'chart_metric_reviews'"
                )
            )
            assert review_policies == 3
    finally:
        engine.dispose()


def test_development_team_creation_with_real_rls_and_rollback() -> None:
    if os.getenv("PLAYERIQ_LIVE_TEST") != "development":
        pytest.skip("Opt in to development-only team checks; all synthetic writes roll back")
    project_ref = os.getenv("PLAYERIQ_TEST_PROJECT_REF")
    settings = get_settings()
    if not project_ref or not settings.database_url or not settings.worker_database_url:
        pytest.skip("Project-matched restricted API and worker connections are required")
    assert settings.supabase_url == f"https://{project_ref}.supabase.co"
    for configured in (settings.database_url, settings.worker_database_url):
        url = make_url(configured)
        assert url.host == f"db.{project_ref}.supabase.co" or (url.username or "").endswith(f".{project_ref}")
    api_engine = make_engine(settings.database_url)
    worker_engine = make_engine(settings.worker_database_url)
    api_engine.hide_parameters = worker_engine.hide_parameters = True
    api = Database(api_engine)
    worker = Database(worker_engine, expected_role="playeriq_worker")

    class RollbackTeamProbe(Exception):
        pass

    try:
        # Read only uploader identity metadata, never PDF bytes, names or values.
        with worker.worker_transaction() as session:
            actor = session.scalar(select(ReportUpload.uploaded_by_user_id).limit(1))
        if actor is None:
            pytest.skip("A development uploader with an owned player profile is required")
        with api.user_transaction(actor) as session:
            before = tuple(t.id for t in list_teams(session, actor).items)
        with pytest.raises(RollbackTeamProbe):
            with api.user_transaction(actor) as session:
                created = create_team(session, actor, "Synthetic rollback FC's")
                assert created.role == "admin"
                assert session.get(TeamManagerGrant, (created.id, actor)) is not None
                assert any(t.id == created.id for t in list_teams(session, actor).items)
                assert team_dashboard(session, actor, created.id).team.role == "admin"
                assert (
                    session.scalar(text("SELECT playeriq.is_team_creator(:team_id)"), {"team_id": created.id}) is True
                )
                unrelated_actor = uuid4()
                session.execute(
                    text("SELECT set_config('playeriq.current_user_id', :actor, true)"),
                    {"actor": str(unrelated_actor)},
                )
                assert session.scalar(select(Team.id).where(Team.id == created.id)) is None
                assert (
                    session.scalar(select(TeamMembership.team_id).where(TeamMembership.team_id == created.id)) is None
                )
                assert (
                    session.scalar(text("SELECT playeriq.is_team_creator(:team_id)"), {"team_id": created.id}) is False
                )
                with pytest.raises(AppError) as denied:
                    team_dashboard(session, unrelated_actor, created.id)
                assert denied.value.status_code == 404
                for row in (
                    TeamMembership(team_id=created.id, user_id=unrelated_actor, role="admin"),
                    TeamManagerGrant(team_id=created.id, user_id=unrelated_actor),
                ):
                    with session.begin_nested() as savepoint:
                        try:
                            session.add(row)
                            session.flush()
                        except DBAPIError as exc:
                            assert getattr(exc.orig, "sqlstate", None) == "42501"
                            savepoint.rollback()
                        else:
                            pytest.fail("Unrelated actor was able to grant team access")
                raise RollbackTeamProbe()
        with api.user_transaction(actor) as session:
            assert tuple(t.id for t in list_teams(session, actor).items) == before
    finally:
        api_engine.dispose()
        worker_engine.dispose()


def test_development_roster_import_real_roles_and_rollback() -> None:
    if os.getenv("PLAYERIQ_LIVE_TEST") != "development":
        pytest.skip("Opt in to synthetic development import checks")
    fixture_id = os.getenv("PLAYERIQ_TEST_SYNTHETIC_UPLOAD_ID")
    if not fixture_id:
        pytest.skip("An externally prepared synthetic fixture with bounded cleanup is required")
    settings = get_settings()
    ref = os.getenv("PLAYERIQ_TEST_PROJECT_REF")
    assert ref == "zlvsslynbajfbwpjywxg" and settings.supabase_url == f"https://{ref}.supabase.co"
    for url_string in (settings.database_url, settings.worker_database_url):
        assert url_string
        parsed = make_url(url_string)
        assert parsed.host == f"db.{ref}.supabase.co" or (parsed.username or "").endswith(f".{ref}")
    api_engine, worker_engine = make_engine(settings.database_url), make_engine(settings.worker_database_url)
    api_engine.hide_parameters = worker_engine.hide_parameters = True
    api, worker = Database(api_engine), Database(worker_engine, expected_role="playeriq_worker")
    upload_id = UUID(fixture_id)

    class RollbackImportProbe(Exception):
        pass

    try:
        with worker.worker_transaction() as session:
            upload = session.get(ReportUpload, upload_id)
            assert upload and upload.original_filename == "synthetic-roster-rls-probe.pdf"
            rows = session.scalars(select(SourceAthleteRow).where(SourceAthleteRow.report_upload_id == upload_id)).all()
            assert len(rows) == 18 and all(r.source_name.startswith("ATHLETE") for r in rows)
            actor = upload.uploaded_by_user_id
            with pytest.raises(DBAPIError) as denied:
                with session.begin_nested():
                    session.execute(select(Player.id).limit(1))
            assert getattr(denied.value.orig, "sqlstate", None) == "42501"
        with pytest.raises(RollbackImportProbe):
            with api.user_transaction(actor) as session:
                created = create_team(session, actor, "Synthetic roster rollback FC")
                body = TeamImportRequest(team_id=created.id, confirm_share=True, session_type="training")
                request_import(session, actor, upload_id, body)
                lock_resource(session, "team-roster", str(created.id))
                from hashlib import sha256

                key = int.from_bytes(
                    sha256(f"playeriq:team-roster:{created.id}".encode()).digest()[:8], "big", signed=True
                )
                with api.user_transaction(actor) as contender:
                    assert contender.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": key}) is False
                execute_import(session, actor, upload_id, settings)
                result = import_out(session, actor, upload_id)
                assert result.counts["created_players"] == 18 and result.counts["accepted_session"] == 15
                ids = [r.player_id for r in result.rows]
                assert len(session.scalars(select(TeamRoster).where(TeamRoster.team_id == created.id)).all()) == 19
                execute_import(session, actor, upload_id, settings)
                assert import_out(session, actor, upload_id).counts == result.counts
                first = result.rows[0]
                assert first.player_id and first.session_id and created.player_id
                # PostgreSQL must refuse unaudited canonical reassignment, even
                # though ordinary team assignment has a permissive UPDATE policy.
                with pytest.raises(DBAPIError) as denied:
                    with session.begin_nested():
                        session.execute(
                            text("UPDATE playeriq.player_sessions SET player_id=:target WHERE id=:session"),
                            {"target": created.player_id, "session": first.session_id},
                        )
                assert getattr(denied.value.orig, "sqlstate", None) == "42501"
                resolved = resolve_row(
                    session,
                    actor,
                    upload_id,
                    first.row_id,
                    ImportResolution(
                        player_id=created.player_id, confirmed_source_label=first.source_name, confirm_association=True
                    ),
                    settings,
                )
                assert resolved.rows[0].session_id == first.session_id
                assert session.get(PlayerSession, first.session_id).player_id == created.player_id
                assert session.get(Player, first.player_id).owner_user_id is None
                other_team = create_team(session, actor, "Synthetic other roster rollback FC")
                assert not session.scalars(
                    select(TeamRoster).where(TeamRoster.team_id == other_team.id, TeamRoster.player_id.in_(ids))
                ).all()
                privileges = session.execute(
                    text(
                        "SELECT has_column_privilege(current_user,'playeriq.players','owner_user_id','UPDATE'), "
                        "has_table_privilege('playeriq_worker','playeriq.player_sessions','SELECT'), "
                        "has_table_privilege('authenticated','playeriq.team_roster','SELECT'), "
                        "has_table_privilege('playeriq_worker','playeriq.team_report_imports','UPDATE')"
                    )
                ).one()
                assert tuple(privileges) == (False, False, False, False)
                session.execute(
                    text("SELECT set_config('playeriq.current_user_id',:actor,true)"), {"actor": str(uuid4())}
                )
                assert not session.scalars(select(TeamRoster).where(TeamRoster.team_id == created.id)).all()
                assert not session.scalars(
                    select(SourceAthleteRow).where(SourceAthleteRow.report_upload_id == upload_id)
                ).all()
                with pytest.raises(AppError) as denied_import:
                    import_out(session, uuid4(), upload_id)
                assert denied_import.value.status_code == 404
                raise RollbackImportProbe()
        with worker.worker_transaction() as session:
            assert session.get(ReportUpload, upload_id).team_id is None
    finally:
        api_engine.dispose()
        worker_engine.dispose()
