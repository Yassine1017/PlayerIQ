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
                    "('report_uploads', 'source_athlete_rows', 'player_sessions', "
                    "'session_metric_values', 'chart_metric_reviews')"
                )
            ).all()
            assert len(tables) == 5
            assert all(row[1] and row[2] for row in tables)
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
