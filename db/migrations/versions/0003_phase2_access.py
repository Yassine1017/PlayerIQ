"""Restricted backend roles and Phase 2 row-level policies.

Revision ID: 0003_phase2_access
Revises: 0002_ingestion_findings

Login credentials are never created by this migration. An operator grants these
NOLOGIN roles to separate private API/worker login roles after migration.
"""

from alembic import op

revision = "0003_phase2_access"
down_revision = "0002_ingestion_findings"
branch_labels = None
depends_on = None

ACTOR = "nullif(current_setting('playeriq.current_user_id', true), '')::uuid"
PLAYER_ACCESS = f"""EXISTS (
    SELECT 1 FROM playeriq.players p
    WHERE p.id = player_id AND p.archived_at IS NULL
      AND (p.owner_user_id = {ACTOR} OR EXISTS (
        SELECT 1 FROM playeriq.player_coaches pc
        WHERE pc.player_id = p.id AND pc.coach_user_id = {ACTOR}
          AND pc.revoked_at IS NULL
      ))
)"""
UPLOAD_OWNER = f"""EXISTS (
    SELECT 1 FROM playeriq.report_uploads u
    WHERE u.id = report_upload_id AND u.uploaded_by_user_id = {ACTOR}
)"""


def _policy(name: str, table: str, action: str, expression: str, check: str | None = None) -> None:
    sql = f"CREATE POLICY {name} ON playeriq.{table} FOR {action} TO playeriq_api"
    if action != "INSERT":
        sql += f" USING ({expression})"
    if action in ("INSERT", "UPDATE"):
        sql += f" WITH CHECK ({check or expression})"
    op.execute(sql)


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'playeriq_api') THEN
            CREATE ROLE playeriq_api NOLOGIN;
          END IF;
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'playeriq_worker') THEN
            CREATE ROLE playeriq_worker NOLOGIN;
          END IF;
        END $$
    """)
    op.execute("REVOKE ALL ON SCHEMA playeriq FROM PUBLIC, anon, authenticated")
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA playeriq FROM PUBLIC, anon, authenticated")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA playeriq REVOKE ALL ON TABLES FROM PUBLIC, anon, authenticated")
    for table in (
        "profiles",
        "players",
        "coach_invitations",
        "player_coaches",
        "report_uploads",
        "ingestion_jobs",
        "activity_reports",
        "report_periods",
        "source_athlete_rows",
        "source_metric_observations",
        "ingestion_findings",
        "player_sessions",
        "session_metric_values",
        "chat_threads",
        "chat_messages",
        "ai_runs",
        "ai_tool_calls",
    ):
        op.execute(f"ALTER TABLE playeriq.{table} FORCE ROW LEVEL SECURITY")
    op.execute("GRANT USAGE ON SCHEMA playeriq TO playeriq_api, playeriq_worker")
    for grant in (
        "GRANT SELECT, INSERT, UPDATE ON playeriq.profiles TO playeriq_api",
        "GRANT SELECT, INSERT ON playeriq.players TO playeriq_api",
        "GRANT SELECT ON playeriq.player_coaches TO playeriq_api",
        "GRANT SELECT, INSERT ON playeriq.report_uploads TO playeriq_api",
        "GRANT INSERT ON playeriq.ingestion_jobs TO playeriq_api",
        "GRANT SELECT ON playeriq.activity_reports, playeriq.report_periods, "
        "playeriq.source_athlete_rows, playeriq.source_metric_observations, "
        "playeriq.ingestion_findings TO playeriq_api",
        "GRANT SELECT, INSERT ON playeriq.player_sessions, playeriq.session_metric_values TO playeriq_api",
        "GRANT SELECT, UPDATE ON playeriq.report_uploads, playeriq.ingestion_jobs TO playeriq_worker",
        "GRANT SELECT, INSERT ON playeriq.activity_reports, playeriq.report_periods, "
        "playeriq.source_athlete_rows, playeriq.source_metric_observations, "
        "playeriq.ingestion_findings TO playeriq_worker",
    ):
        op.execute(grant)

    _policy("profiles_self_select", "profiles", "SELECT", f"user_id = {ACTOR}")
    _policy("profiles_self_insert", "profiles", "INSERT", f"user_id = {ACTOR}")
    _policy("profiles_self_update", "profiles", "UPDATE", f"user_id = {ACTOR}")
    _policy(
        "players_owner_or_coach_select",
        "players",
        "SELECT",
        f"owner_user_id = {ACTOR} OR EXISTS (SELECT 1 FROM playeriq.player_coaches pc "
        f"WHERE pc.player_id = id AND pc.coach_user_id = {ACTOR} AND pc.revoked_at IS NULL)",
    )
    _policy("players_owner_insert", "players", "INSERT", f"owner_user_id = {ACTOR}")
    _policy("player_coaches_self_select", "player_coaches", "SELECT", f"coach_user_id = {ACTOR}")
    _policy("report_uploads_owner_select", "report_uploads", "SELECT", f"uploaded_by_user_id = {ACTOR}")
    _policy("report_uploads_owner_insert", "report_uploads", "INSERT", f"uploaded_by_user_id = {ACTOR}")
    _policy(
        "ingestion_jobs_owner_insert",
        "ingestion_jobs",
        "INSERT",
        f"EXISTS (SELECT 1 FROM playeriq.report_uploads u WHERE u.id = upload_id AND u.uploaded_by_user_id = {ACTOR})",
    )
    _policy("activity_reports_owner_select", "activity_reports", "SELECT", UPLOAD_OWNER)
    _policy("report_periods_owner_select", "report_periods", "SELECT", UPLOAD_OWNER)
    _policy("source_rows_owner_select", "source_athlete_rows", "SELECT", UPLOAD_OWNER)
    _policy("ingestion_findings_owner_select", "ingestion_findings", "SELECT", UPLOAD_OWNER)
    _policy(
        "source_metrics_owner_select",
        "source_metric_observations",
        "SELECT",
        f"(report_upload_id IS NOT NULL AND {UPLOAD_OWNER}) OR "
        f"EXISTS (SELECT 1 FROM playeriq.source_athlete_rows r JOIN playeriq.report_uploads u "
        f"ON u.id = r.report_upload_id WHERE r.id = athlete_row_id AND u.uploaded_by_user_id = {ACTOR}) OR "
        f"EXISTS (SELECT 1 FROM playeriq.report_periods p JOIN playeriq.report_uploads u "
        f"ON u.id = p.report_upload_id WHERE p.id = period_id AND u.uploaded_by_user_id = {ACTOR})",
    )
    _policy("player_sessions_access_select", "player_sessions", "SELECT", PLAYER_ACCESS)
    _policy(
        "player_sessions_access_insert",
        "player_sessions",
        "INSERT",
        f"EXISTS (SELECT 1 FROM playeriq.players p WHERE p.id = player_id "
        f"AND p.owner_user_id = {ACTOR} AND p.archived_at IS NULL) "
        f"AND EXISTS (SELECT 1 FROM playeriq.source_athlete_rows r "
        f"JOIN playeriq.report_uploads u ON u.id = r.report_upload_id "
        f"WHERE r.id = source_athlete_row_id AND u.uploaded_by_user_id = {ACTOR})",
    )
    _policy(
        "session_metrics_access_select",
        "session_metric_values",
        "SELECT",
        "EXISTS (SELECT 1 FROM playeriq.player_sessions s WHERE s.id = player_session_id)",
    )
    _policy(
        "session_metrics_access_insert",
        "session_metric_values",
        "INSERT",
        "EXISTS (SELECT 1 FROM playeriq.player_sessions s WHERE s.id = player_session_id)",
    )
    for table in (
        "report_uploads",
        "ingestion_jobs",
        "activity_reports",
        "report_periods",
        "source_athlete_rows",
        "source_metric_observations",
        "ingestion_findings",
    ):
        op.execute(
            f"CREATE POLICY {table}_worker_all ON playeriq.{table} "
            "FOR ALL TO playeriq_worker USING (true) WITH CHECK (true)"
        )


def downgrade() -> None:
    for table in (
        "profiles",
        "players",
        "coach_invitations",
        "player_coaches",
        "report_uploads",
        "ingestion_jobs",
        "activity_reports",
        "report_periods",
        "source_athlete_rows",
        "source_metric_observations",
        "ingestion_findings",
        "player_sessions",
        "session_metric_values",
        "chat_threads",
        "chat_messages",
        "ai_runs",
        "ai_tool_calls",
    ):
        op.execute(f"ALTER TABLE playeriq.{table} NO FORCE ROW LEVEL SECURITY")
    for table, names in {
        "profiles": ["profiles_self_select", "profiles_self_insert", "profiles_self_update"],
        "players": ["players_owner_or_coach_select", "players_owner_insert"],
        "player_coaches": ["player_coaches_self_select"],
        "report_uploads": ["report_uploads_owner_select", "report_uploads_owner_insert"],
        "ingestion_jobs": ["ingestion_jobs_owner_insert"],
        "activity_reports": ["activity_reports_owner_select"],
        "report_periods": ["report_periods_owner_select"],
        "source_athlete_rows": ["source_rows_owner_select"],
        "source_metric_observations": ["source_metrics_owner_select"],
        "ingestion_findings": ["ingestion_findings_owner_select"],
        "player_sessions": ["player_sessions_access_select", "player_sessions_access_insert"],
        "session_metric_values": ["session_metrics_access_select", "session_metrics_access_insert"],
    }.items():
        for name in names:
            op.execute(f"DROP POLICY IF EXISTS {name} ON playeriq.{table}")
    for table in (
        "report_uploads",
        "ingestion_jobs",
        "activity_reports",
        "report_periods",
        "source_athlete_rows",
        "source_metric_observations",
        "ingestion_findings",
    ):
        op.execute(f"DROP POLICY IF EXISTS {table}_worker_all ON playeriq.{table}")
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA playeriq FROM playeriq_api, playeriq_worker")
    op.execute("REVOKE USAGE ON SCHEMA playeriq FROM playeriq_api, playeriq_worker")
    # Roles are intentionally retained: login-role membership is external and
    # dropping them in a rollback could disrupt other deployments.
