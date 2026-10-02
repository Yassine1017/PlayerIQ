"""Confirmed source identities and private team workspace.

Revision ID: 0009_player_identity_teams
Revises: 0008_ai_budget_precision
"""

import sqlalchemy as sa
from alembic import op

revision = "0009_player_identity_teams"
down_revision = "0008_ai_budget_precision"
branch_labels = None
depends_on = None

ACTOR = "nullif(current_setting('playeriq.current_user_id', true), '')::uuid"


def manager(table: str) -> str:
    return (
        "EXISTS (SELECT 1 FROM playeriq.team_manager_grants g "
        f"WHERE g.team_id = playeriq.{table}.team_id AND g.user_id = {ACTOR})"
    )


def member(table: str) -> str:
    return (
        "EXISTS (SELECT 1 FROM playeriq.team_memberships m "
        f"WHERE m.team_id = playeriq.{table}.team_id AND m.user_id = {ACTOR} AND m.revoked_at IS NULL)"
    )


def upgrade() -> None:
    op.create_table(
        "teams",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), sa.ForeignKey("auth.users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="playeriq",
    )
    op.create_table(
        "team_memberships",
        sa.Column("team_id", sa.Uuid(), sa.ForeignKey("playeriq.teams.id"), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("auth.users.id"), primary_key=True),
        sa.Column("player_id", sa.Uuid(), sa.ForeignKey("playeriq.players.id")),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("role IN ('player','coach','admin')", name="team_role"),
        schema="playeriq",
    )
    op.create_index("ix_team_memberships_player", "team_memberships", ["player_id"], schema="playeriq")
    op.create_table(
        "team_manager_grants",
        sa.Column("team_id", sa.Uuid(), sa.ForeignKey("playeriq.teams.id"), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("auth.users.id"), primary_key=True),
        schema="playeriq",
    )
    op.create_table(
        "team_join_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("team_id", sa.Uuid(), sa.ForeignKey("playeriq.teams.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("auth.users.id"), nullable=False),
        sa.Column("player_id", sa.Uuid(), sa.ForeignKey("playeriq.players.id")),
        sa.Column("display_name_snapshot", sa.String(160), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("decided_by_user_id", sa.Uuid(), sa.ForeignKey("auth.users.id")),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('pending','approved','declined')", name="join_status"),
        schema="playeriq",
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_team_join_pending ON playeriq.team_join_requests (team_id, user_id) "
        "WHERE status = 'pending'"
    )
    op.create_table(
        "player_source_identities",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("player_id", sa.Uuid(), sa.ForeignKey("playeriq.players.id"), nullable=False),
        sa.Column("team_id", sa.Uuid(), sa.ForeignKey("playeriq.teams.id")),
        sa.Column("scope_key", sa.String(300), nullable=False),
        sa.Column("parser_key", sa.String(100), nullable=False),
        sa.Column("normalized_label", sa.String(255), nullable=False),
        sa.Column("original_label", sa.String(255), nullable=False),
        sa.Column("confirmed_row_id", sa.Uuid(), sa.ForeignKey("playeriq.source_athlete_rows.id"), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), sa.ForeignKey("auth.users.id"), nullable=False),
        sa.Column("confirmed_by_user_id", sa.Uuid(), sa.ForeignKey("auth.users.id"), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="playeriq",
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_source_identity_active ON playeriq.player_source_identities "
        "(scope_key, parser_key, normalized_label) WHERE revoked_at IS NULL"
    )
    op.create_index(
        "ix_source_identity_player", "player_source_identities", ["player_id", "revoked_at"], schema="playeriq"
    )
    op.add_column(
        "report_uploads", sa.Column("team_id", sa.Uuid(), sa.ForeignKey("playeriq.teams.id")), schema="playeriq"
    )
    op.create_index("ix_report_uploads_team", "report_uploads", ["team_id", "created_at"], schema="playeriq")
    op.add_column(
        "player_sessions",
        sa.Column("report_upload_id", sa.Uuid(), sa.ForeignKey("playeriq.report_uploads.id")),
        schema="playeriq",
    )
    op.execute(
        "UPDATE playeriq.player_sessions s SET report_upload_id = r.report_upload_id "
        "FROM playeriq.source_athlete_rows r WHERE r.id = s.source_athlete_row_id"
    )
    op.alter_column("player_sessions", "report_upload_id", nullable=False, schema="playeriq")
    op.add_column(
        "player_sessions", sa.Column("team_id", sa.Uuid(), sa.ForeignKey("playeriq.teams.id")), schema="playeriq"
    )
    op.add_column(
        "player_sessions",
        sa.Column("link_method", sa.String(16), nullable=False, server_default="manual"),
        schema="playeriq",
    )
    op.add_column(
        "player_sessions",
        sa.Column("source_identity_id", sa.Uuid(), sa.ForeignKey("playeriq.player_source_identities.id")),
        schema="playeriq",
    )
    op.create_check_constraint(
        "link_method", "player_sessions", "link_method IN ('manual','recognized')", schema="playeriq"
    )
    op.create_index(
        "ix_player_sessions_team_report", "player_sessions", ["team_id", "report_upload_id"], schema="playeriq"
    )

    for table in ("teams", "team_memberships", "team_manager_grants", "team_join_requests", "player_source_identities"):
        op.execute(f"ALTER TABLE playeriq.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE playeriq.{table} FORCE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON playeriq.{table} FROM PUBLIC, anon, authenticated")
    op.execute("GRANT SELECT, INSERT ON playeriq.teams TO playeriq_api")
    op.execute("GRANT SELECT, INSERT ON playeriq.team_memberships, playeriq.team_manager_grants TO playeriq_api")
    op.execute("GRANT SELECT, INSERT ON playeriq.team_join_requests TO playeriq_api")
    op.execute("GRANT UPDATE (status, decided_by_user_id, decided_at) ON playeriq.team_join_requests TO playeriq_api")
    op.execute("GRANT SELECT, INSERT ON playeriq.player_source_identities TO playeriq_api")
    op.execute("GRANT UPDATE (revoked_at) ON playeriq.player_source_identities TO playeriq_api")
    op.execute("GRANT UPDATE (team_id) ON playeriq.report_uploads TO playeriq_api")
    op.execute("GRANT UPDATE (team_id, report_upload_id) ON playeriq.player_sessions TO playeriq_api")

    op.execute(
        "CREATE POLICY teams_member_select ON playeriq.teams FOR SELECT TO playeriq_api "
        f"USING (created_by_user_id = {ACTOR} OR EXISTS (SELECT 1 FROM playeriq.team_memberships m "
        f"WHERE m.team_id = id AND m.user_id = {ACTOR} AND m.revoked_at IS NULL))"
    )
    op.execute(
        "CREATE POLICY teams_creator_insert ON playeriq.teams FOR INSERT TO playeriq_api "
        f"WITH CHECK (created_by_user_id = {ACTOR})"
    )
    op.execute(
        "CREATE POLICY team_manager_grants_self_select ON playeriq.team_manager_grants "
        f"FOR SELECT TO playeriq_api USING (user_id = {ACTOR})"
    )
    op.execute(
        "CREATE POLICY team_manager_grants_creator_insert ON playeriq.team_manager_grants "
        f"FOR INSERT TO playeriq_api WITH CHECK (EXISTS (SELECT 1 FROM playeriq.teams t "
        f"WHERE t.id = team_id AND t.created_by_user_id = {ACTOR}))"
    )
    op.execute(
        "CREATE POLICY team_memberships_scoped_select ON playeriq.team_memberships FOR SELECT TO playeriq_api "
        f"USING (user_id = {ACTOR} OR {manager('team_memberships')})"
    )
    op.execute(
        "CREATE POLICY team_memberships_creator_insert ON playeriq.team_memberships FOR INSERT TO playeriq_api "
        f"WITH CHECK (EXISTS (SELECT 1 FROM playeriq.teams t "
        f"WHERE t.id = team_id AND t.created_by_user_id = {ACTOR}))"
    )
    op.execute(
        "CREATE POLICY team_join_requests_scoped_select ON playeriq.team_join_requests FOR SELECT TO playeriq_api "
        f"USING (user_id = {ACTOR} OR {manager('team_join_requests')})"
    )
    op.execute(
        "CREATE POLICY team_join_requests_self_insert ON playeriq.team_join_requests FOR INSERT TO playeriq_api "
        f"WITH CHECK (user_id = {ACTOR} AND status = 'pending' AND "
        f"EXISTS (SELECT 1 FROM playeriq.players p WHERE p.id = playeriq.team_join_requests.player_id "
        f"AND p.owner_user_id = {ACTOR} AND p.archived_at IS NULL))"
    )
    op.execute(
        "CREATE POLICY team_join_requests_admin_update ON playeriq.team_join_requests FOR UPDATE TO playeriq_api "
        f"USING ({manager('team_join_requests')}) "
        f"WITH CHECK ({manager('team_join_requests')} AND decided_by_user_id = {ACTOR})"
    )
    op.execute(
        "CREATE POLICY source_identities_owner_manager_select ON playeriq.player_source_identities "
        "FOR SELECT TO playeriq_api "
        f"USING (EXISTS (SELECT 1 FROM playeriq.players p WHERE p.id = player_id AND p.owner_user_id = {ACTOR}) "
        f"OR (team_id IS NOT NULL AND {manager('player_source_identities')}))"
    )
    op.execute(
        "CREATE POLICY source_identities_owner_insert ON playeriq.player_source_identities "
        "FOR INSERT TO playeriq_api WITH CHECK ("
        f"created_by_user_id = {ACTOR} AND confirmed_by_user_id = {ACTOR} "
        "AND ("
        f"EXISTS (SELECT 1 FROM playeriq.players p WHERE p.id = player_id AND p.owner_user_id = {ACTOR}) "
        f"OR (team_id IS NOT NULL AND {manager('player_source_identities')} "
        "AND EXISTS (SELECT 1 FROM playeriq.team_memberships m "
        "WHERE m.team_id = playeriq.player_source_identities.team_id "
        "AND m.player_id = playeriq.player_source_identities.player_id AND m.revoked_at IS NULL))) "
        f"AND EXISTS (SELECT 1 FROM playeriq.source_athlete_rows r JOIN playeriq.report_uploads u "
        f"ON u.id = r.report_upload_id WHERE r.id = confirmed_row_id AND u.uploaded_by_user_id = {ACTOR} "
        "AND u.team_id IS NOT DISTINCT FROM playeriq.player_source_identities.team_id))"
    )
    op.execute(
        "CREATE POLICY source_identities_owner_update ON playeriq.player_source_identities "
        "FOR UPDATE TO playeriq_api "
        f"USING (EXISTS (SELECT 1 FROM playeriq.players p WHERE p.id = player_id AND p.owner_user_id = {ACTOR})) "
        f"WITH CHECK (EXISTS (SELECT 1 FROM playeriq.players p WHERE p.id = player_id AND p.owner_user_id = {ACTOR}))"
    )
    op.execute(
        "CREATE POLICY players_team_manager_select ON playeriq.players FOR SELECT TO playeriq_api "
        f"USING (EXISTS (SELECT 1 FROM playeriq.team_memberships m JOIN playeriq.team_manager_grants g "
        f"ON g.team_id = m.team_id WHERE m.player_id = id AND m.revoked_at IS NULL AND g.user_id = {ACTOR}))"
    )
    op.execute(
        "CREATE POLICY players_pending_team_manager_select ON playeriq.players FOR SELECT TO playeriq_api "
        "USING (EXISTS (SELECT 1 FROM playeriq.team_join_requests j "
        "JOIN playeriq.team_manager_grants g ON g.team_id = j.team_id "
        f"WHERE j.player_id = playeriq.players.id AND j.status = 'pending' AND g.user_id = {ACTOR}))"
    )
    op.execute("DROP POLICY report_uploads_owner_insert ON playeriq.report_uploads")
    op.execute(
        "CREATE POLICY report_uploads_owner_insert ON playeriq.report_uploads FOR INSERT TO playeriq_api "
        f"WITH CHECK (uploaded_by_user_id = {ACTOR} AND (team_id IS NULL OR {manager('report_uploads')}))"
    )
    op.execute(
        "CREATE POLICY report_uploads_owner_team_update ON playeriq.report_uploads FOR UPDATE TO playeriq_api "
        f"USING (uploaded_by_user_id = {ACTOR}) "
        f"WITH CHECK (uploaded_by_user_id = {ACTOR} AND (team_id IS NULL OR {manager('report_uploads')}))"
    )
    op.execute(
        "CREATE POLICY report_uploads_team_manager_select ON playeriq.report_uploads FOR SELECT TO playeriq_api "
        f"USING (team_id IS NOT NULL AND {manager('report_uploads')})"
    )
    op.execute(
        "CREATE POLICY player_sessions_team_member_select ON playeriq.player_sessions FOR SELECT TO playeriq_api "
        f"USING (team_id IS NOT NULL AND quality_state = 'accepted' AND {member('player_sessions')})"
    )
    op.execute(
        "CREATE POLICY player_sessions_team_manager_insert ON playeriq.player_sessions FOR INSERT TO playeriq_api "
        f"WITH CHECK (team_id IS NOT NULL AND {manager('player_sessions')} AND "
        "EXISTS (SELECT 1 FROM playeriq.team_memberships m WHERE m.team_id = playeriq.player_sessions.team_id "
        "AND m.player_id = playeriq.player_sessions.player_id AND m.revoked_at IS NULL) AND "
        f"EXISTS (SELECT 1 FROM playeriq.source_athlete_rows r JOIN playeriq.report_uploads u "
        f"ON u.id = r.report_upload_id WHERE r.id = playeriq.player_sessions.source_athlete_row_id "
        f"AND u.id = playeriq.player_sessions.report_upload_id "
        f"AND u.team_id = playeriq.player_sessions.team_id AND u.uploaded_by_user_id = {ACTOR}))"
    )
    op.execute(
        "CREATE POLICY player_sessions_team_assignment_update ON playeriq.player_sessions FOR UPDATE TO playeriq_api "
        f"USING (EXISTS (SELECT 1 FROM playeriq.source_athlete_rows r JOIN playeriq.report_uploads u "
        f"ON u.id = r.report_upload_id WHERE r.id = source_athlete_row_id AND u.uploaded_by_user_id = {ACTOR})) "
        f"WITH CHECK (team_id IS NOT NULL AND {manager('player_sessions')} AND "
        "EXISTS (SELECT 1 FROM playeriq.source_athlete_rows r JOIN playeriq.report_uploads u "
        "ON u.id = r.report_upload_id WHERE r.id = playeriq.player_sessions.source_athlete_row_id "
        "AND u.id = playeriq.player_sessions.report_upload_id "
        "AND u.team_id = playeriq.player_sessions.team_id) AND "
        "EXISTS (SELECT 1 FROM playeriq.team_memberships m "
        "WHERE m.team_id = playeriq.player_sessions.team_id "
        "AND m.player_id = playeriq.player_sessions.player_id AND m.revoked_at IS NULL))"
    )


def downgrade() -> None:
    for table, policies in {
        "player_sessions": (
            "player_sessions_team_assignment_update",
            "player_sessions_team_manager_insert",
            "player_sessions_team_member_select",
        ),
        "report_uploads": ("report_uploads_team_manager_select", "report_uploads_owner_team_update"),
        "players": ("players_pending_team_manager_select", "players_team_manager_select"),
    }.items():
        for policy in policies:
            op.execute(f"DROP POLICY IF EXISTS {policy} ON playeriq.{table}")
    op.execute("DROP POLICY report_uploads_owner_insert ON playeriq.report_uploads")
    op.execute(
        "CREATE POLICY report_uploads_owner_insert ON playeriq.report_uploads FOR INSERT TO playeriq_api "
        f"WITH CHECK (uploaded_by_user_id = {ACTOR})"
    )
    op.drop_index("ix_player_sessions_team_report", table_name="player_sessions", schema="playeriq")
    op.drop_constraint("link_method", "player_sessions", type_="check", schema="playeriq")
    for column in ("source_identity_id", "link_method", "team_id", "report_upload_id"):
        op.drop_column("player_sessions", column, schema="playeriq")
    op.drop_index("ix_report_uploads_team", table_name="report_uploads", schema="playeriq")
    op.drop_column("report_uploads", "team_id", schema="playeriq")
    for table in ("player_source_identities", "team_join_requests", "team_manager_grants", "team_memberships", "teams"):
        op.drop_table(table, schema="playeriq")
