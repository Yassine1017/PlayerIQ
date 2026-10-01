"""Read-only development Supabase checks, disabled unless explicitly opted in."""

import os

import pytest
from app.db.session import Database, make_engine
from sqlalchemy import text


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
