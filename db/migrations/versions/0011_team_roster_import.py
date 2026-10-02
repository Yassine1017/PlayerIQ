"""Unclaimed canonical roster athletes and auditable, restricted team imports.

Revision ID: 0011_team_roster_import
Revises: 0010_team_creation_rls
"""

import sqlalchemy as sa
from alembic import op

revision = "0011_team_roster_import"
down_revision = "0010_team_creation_rls"
branch_labels = None
depends_on = None

ACTOR = "nullif(current_setting('playeriq.current_user_id', true), '')::uuid"


def manager(table: str) -> str:
    return (
        "EXISTS (SELECT 1 FROM playeriq.team_manager_grants g "
        f"WHERE g.team_id = playeriq.{table}.team_id AND g.user_id = {ACTOR})"
    )


def policy(table: str, name: str, operation: str, expression: str) -> None:
    clause = "WITH CHECK" if operation == "INSERT" else "USING"
    op.execute(f"CREATE POLICY {name} ON playeriq.{table} FOR {operation} TO playeriq_api {clause} ({expression})")


def upgrade() -> None:
    op.alter_column("players", "owner_user_id", nullable=True, schema="playeriq")
    op.add_column(
        "players", sa.Column("origin_team_id", sa.Uuid(), sa.ForeignKey("playeriq.teams.id")), schema="playeriq"
    )
    op.create_check_constraint(
        "player_origin", "players", "owner_user_id IS NOT NULL OR origin_team_id IS NOT NULL", schema="playeriq"
    )
    op.create_index("ix_players_origin_team", "players", ["origin_team_id"], schema="playeriq")
    op.create_table(
        "team_roster",
        sa.Column("team_id", sa.Uuid(), sa.ForeignKey("playeriq.teams.id"), primary_key=True),
        sa.Column("player_id", sa.Uuid(), sa.ForeignKey("playeriq.players.id"), primary_key=True),
        sa.Column("parser_key", sa.String(100)),
        sa.Column("normalized_label", sa.String(255)),
        sa.Column("source_row_id", sa.Uuid(), sa.ForeignKey("playeriq.source_athlete_rows.id")),
        sa.Column("added_by_user_id", sa.Uuid(), sa.ForeignKey("auth.users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        schema="playeriq",
    )
    op.create_index("ix_team_roster_player", "team_roster", ["player_id"], schema="playeriq")
    op.create_index(
        "uq_team_roster_source",
        "team_roster",
        ["team_id", "parser_key", "normalized_label"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
        schema="playeriq",
    )
    op.create_table(
        "team_report_imports",
        sa.Column("upload_id", sa.Uuid(), sa.ForeignKey("playeriq.report_uploads.id"), primary_key=True),
        sa.Column("team_id", sa.Uuid(), sa.ForeignKey("playeriq.teams.id"), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), sa.ForeignKey("auth.users.id"), nullable=False),
        sa.Column("session_type", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(80)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('queued','complete','needs_review','failed')", name="import_status"),
        sa.CheckConstraint("session_type IN ('training','match','unknown')", name="import_session_type"),
        sa.CheckConstraint("attempts >= 0 AND attempts <= 3", name="import_attempts"),
        schema="playeriq",
    )
    op.create_index("ix_team_import_queue", "team_report_imports", ["status", "created_at"], schema="playeriq")
    op.create_table(
        "team_report_import_rows",
        sa.Column("row_id", sa.Uuid(), sa.ForeignKey("playeriq.source_athlete_rows.id"), primary_key=True),
        sa.Column("upload_id", sa.Uuid(), sa.ForeignKey("playeriq.team_report_imports.upload_id"), nullable=False),
        sa.Column("player_id", sa.Uuid(), sa.ForeignKey("playeriq.players.id")),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("playeriq.player_sessions.id")),
        sa.Column("association_method", sa.String(32), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("reason_code", sa.String(80)),
        sa.Column("created_player", sa.Boolean(), nullable=False),
        sa.Column("created_session", sa.Boolean(), nullable=False),
        sa.Column("resolved_by_user_id", sa.Uuid(), sa.ForeignKey("auth.users.id")),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        schema="playeriq",
    )
    op.create_index("ix_team_import_rows_upload", "team_report_import_rows", ["upload_id"], schema="playeriq")
    op.create_table(
        "team_roster_resolutions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("team_id", sa.Uuid(), sa.ForeignKey("playeriq.teams.id"), nullable=False),
        sa.Column("from_player_id", sa.Uuid(), sa.ForeignKey("playeriq.players.id"), nullable=False, unique=True),
        sa.Column("to_player_id", sa.Uuid(), sa.ForeignKey("playeriq.players.id"), nullable=False),
        sa.Column("source_row_id", sa.Uuid(), sa.ForeignKey("playeriq.source_athlete_rows.id"), nullable=False),
        sa.Column("confirmed_by_user_id", sa.Uuid(), sa.ForeignKey("auth.users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="playeriq",
    )
    for table in ("team_roster", "team_report_imports", "team_report_import_rows", "team_roster_resolutions"):
        op.execute(f"ALTER TABLE playeriq.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE playeriq.{table} FORCE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON playeriq.{table} FROM PUBLIC, anon, authenticated, playeriq_worker")
        op.execute(f"GRANT SELECT, INSERT ON playeriq.{table} TO playeriq_api")
    op.execute("GRANT UPDATE (revoked_at) ON playeriq.team_roster TO playeriq_api")
    op.execute(
        "GRANT UPDATE (status, attempts, error_code, finished_at) ON playeriq.team_report_imports TO playeriq_api"
    )
    op.execute(
        "GRANT UPDATE (player_id, session_id, association_method, outcome, reason_code, created_player, created_session, resolved_by_user_id, resolved_at) ON playeriq.team_report_import_rows TO playeriq_api"
    )
    op.execute("GRANT SELECT ON playeriq.team_report_imports TO playeriq_worker")
    op.execute(
        "CREATE POLICY import_worker_metadata ON playeriq.team_report_imports FOR SELECT TO playeriq_worker USING (true)"
    )

    # Seed approved existing athletes, without changing memberships or ownership.
    op.execute(
        "INSERT INTO playeriq.team_roster (team_id,player_id,added_by_user_id) "
        "SELECT m.team_id,m.player_id,t.created_by_user_id FROM playeriq.team_memberships m "
        "JOIN playeriq.teams t ON t.id=m.team_id WHERE m.player_id IS NOT NULL AND m.revoked_at IS NULL "
        "ON CONFLICT DO NOTHING"
    )
    policy(
        "team_roster",
        "roster_select",
        "SELECT",
        manager("team_roster") + " OR EXISTS (SELECT 1 FROM playeriq.team_memberships m "
        f"WHERE m.team_id=team_roster.team_id AND m.player_id=team_roster.player_id AND m.user_id={ACTOR} AND m.revoked_at IS NULL)",
    )
    # Non-inlineable invoker lookup prevents INSERT roster -> SELECT player ->
    # SELECT roster recursion. No additional privileges are granted to the helper.
    op.execute("""CREATE FUNCTION playeriq.is_roster_player(p_team uuid, p_player uuid) RETURNS boolean
        LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $body$
        BEGIN RETURN EXISTS (SELECT 1 FROM playeriq.players p WHERE p.id=p_player AND p.archived_at IS NULL
          AND ((p.owner_user_id IS NULL AND p.origin_team_id=p_team) OR EXISTS (
            SELECT 1 FROM playeriq.team_memberships m WHERE m.team_id=p_team AND m.player_id=p.id AND m.revoked_at IS NULL)));
        END; $body$""")
    op.execute(
        "REVOKE ALL ON FUNCTION playeriq.is_roster_player(uuid,uuid) FROM PUBLIC,anon,authenticated,playeriq_worker"
    )
    op.execute("GRANT EXECUTE ON FUNCTION playeriq.is_roster_player(uuid,uuid) TO playeriq_api")
    policy(
        "team_roster",
        "roster_insert",
        "INSERT",
        manager("team_roster") + f" AND added_by_user_id={ACTOR} AND playeriq.is_roster_player(team_id,player_id)",
    )
    policy(
        "players",
        "players_unclaimed_select",
        "SELECT",
        "owner_user_id IS NULL AND EXISTS (SELECT 1 FROM playeriq.team_manager_grants g "
        f"WHERE g.team_id=players.origin_team_id AND g.user_id={ACTOR})",
    )
    policy(
        "players",
        "players_unclaimed_insert",
        "INSERT",
        "owner_user_id IS NULL AND archived_at IS NULL AND EXISTS (SELECT 1 FROM playeriq.team_manager_grants g "
        f"WHERE g.team_id=players.origin_team_id AND g.user_id={ACTOR})",
    )
    owner = f"requested_by_user_id={ACTOR}"
    policy("team_report_imports", "import_owner_select", "SELECT", owner)
    policy(
        "team_report_imports",
        "import_owner_insert",
        "INSERT",
        owner
        + " AND "
        + manager("team_report_imports")
        + f" AND EXISTS (SELECT 1 FROM playeriq.report_uploads u WHERE u.id=upload_id AND u.team_id=team_report_imports.team_id AND u.uploaded_by_user_id={ACTOR})",
    )
    policy("team_report_imports", "import_owner_update", "UPDATE", owner)
    row_owner = f"EXISTS (SELECT 1 FROM playeriq.team_report_imports i WHERE i.upload_id=team_report_import_rows.upload_id AND i.requested_by_user_id={ACTOR})"
    policy("team_report_import_rows", "import_rows_select", "SELECT", row_owner)
    policy(
        "team_report_import_rows",
        "import_rows_insert",
        "INSERT",
        row_owner
        + " AND EXISTS (SELECT 1 FROM playeriq.source_athlete_rows r WHERE r.id=row_id AND r.report_upload_id=team_report_import_rows.upload_id)",
    )
    policy("team_report_import_rows", "import_rows_update", "UPDATE", row_owner)
    roster_check = (
        "EXISTS (SELECT 1 FROM playeriq.team_roster r WHERE r.team_id=player_sessions.team_id "
        "AND r.player_id=player_sessions.player_id AND r.revoked_at IS NULL)"
    )
    source_check = (
        f"EXISTS (SELECT 1 FROM playeriq.source_athlete_rows r JOIN playeriq.report_uploads u ON u.id=r.report_upload_id "
        f"WHERE r.id=player_sessions.source_athlete_row_id AND u.id=player_sessions.report_upload_id "
        f"AND u.team_id=player_sessions.team_id AND u.uploaded_by_user_id={ACTOR})"
    )
    policy(
        "player_sessions",
        "sessions_roster_insert",
        "INSERT",
        manager("player_sessions") + " AND " + roster_check + " AND " + source_check,
    )
    policy(
        "player_source_identities",
        "identities_roster_insert",
        "INSERT",
        manager("player_source_identities")
        + f" AND created_by_user_id={ACTOR} AND confirmed_by_user_id={ACTOR} AND EXISTS (SELECT 1 FROM playeriq.team_roster r "
        "WHERE r.team_id=player_source_identities.team_id AND r.player_id=player_source_identities.player_id AND r.revoked_at IS NULL) "
        f"AND EXISTS (SELECT 1 FROM playeriq.source_athlete_rows r JOIN playeriq.report_uploads u ON u.id=r.report_upload_id "
        f"WHERE r.id=confirmed_row_id AND u.team_id=player_source_identities.team_id AND u.uploaded_by_user_id={ACTOR})",
    )

    policy("team_roster_resolutions", "resolution_select", "SELECT", manager("team_roster_resolutions"))
    policy(
        "team_roster_resolutions",
        "resolution_insert",
        "INSERT",
        manager("team_roster_resolutions") + f" AND confirmed_by_user_id={ACTOR} AND from_player_id<>to_player_id "
        "AND EXISTS (SELECT 1 FROM playeriq.players p WHERE p.id=from_player_id AND p.owner_user_id IS NULL "
        "AND p.origin_team_id=team_roster_resolutions.team_id AND p.archived_at IS NULL) "
        "AND EXISTS (SELECT 1 FROM playeriq.team_memberships m WHERE m.team_id=team_roster_resolutions.team_id "
        "AND m.player_id=to_player_id AND m.revoked_at IS NULL) "
        f"AND EXISTS (SELECT 1 FROM playeriq.source_athlete_rows r JOIN playeriq.report_uploads u ON u.id=r.report_upload_id "
        f"WHERE r.id=source_row_id AND u.team_id=team_roster_resolutions.team_id AND u.uploaded_by_user_id={ACTOR})",
    )
    # Only these columns may change for an audited association. A trigger also
    # checks OLD -> NEW; permissive assignment policies cannot authorize arbitrary relinking.
    op.execute(
        "GRANT UPDATE (player_id) ON playeriq.player_sessions, playeriq.player_source_identities TO playeriq_api"
    )
    op.execute("GRANT UPDATE (archived_at) ON playeriq.players TO playeriq_api")
    for table, source_column, target_column in (
        ("player_sessions", "player_id", "player_id"),
        ("player_source_identities", "player_id", "player_id"),
        ("players", "id", "id"),
        ("team_roster", "player_id", "player_id"),
    ):
        evidence = (
            f"EXISTS (SELECT 1 FROM playeriq.team_roster_resolutions x WHERE x.from_player_id=playeriq.{table}.{source_column} "
            f"AND x.confirmed_by_user_id={ACTOR} AND "
            + manager(table if table != "players" else "team_roster_resolutions")
            + ")"
        )
        # Players has origin_team_id, rather than team_id.
        if table == "players":
            evidence = f"EXISTS (SELECT 1 FROM playeriq.team_roster_resolutions x WHERE x.from_player_id=players.id AND x.confirmed_by_user_id={ACTOR})"
        target = (
            evidence
            if table in ("players", "team_roster")
            else (
                f"EXISTS (SELECT 1 FROM playeriq.team_roster_resolutions x WHERE x.to_player_id={table}.{target_column} "
                f"AND x.team_id={table}.team_id AND x.confirmed_by_user_id={ACTOR})"
            )
        )
        op.execute(
            f"CREATE POLICY {table}_resolution_update ON playeriq.{table} FOR UPDATE TO playeriq_api USING ({evidence}) WITH CHECK ({target})"
        )
    op.execute(f"""CREATE FUNCTION playeriq.guard_roster_association() RETURNS trigger
        LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $body$
        BEGIN
          IF NEW.player_id IS DISTINCT FROM OLD.player_id THEN
            IF NOT EXISTS (SELECT 1 FROM playeriq.team_roster_resolutions x
              WHERE x.from_player_id=OLD.player_id AND x.to_player_id=NEW.player_id
                AND x.team_id=OLD.team_id AND NEW.team_id=OLD.team_id AND x.confirmed_by_user_id={ACTOR}) THEN
              RAISE EXCEPTION USING ERRCODE='42501', MESSAGE='Audited roster association required';
            END IF;
          END IF;
          RETURN NEW;
        END; $body$""")
    op.execute(
        "REVOKE ALL ON FUNCTION playeriq.guard_roster_association() FROM PUBLIC,anon,authenticated,playeriq_worker,playeriq_api"
    )
    for table in ("player_sessions", "player_source_identities"):
        op.execute(
            f"CREATE TRIGGER guard_roster_association BEFORE UPDATE OF player_id ON playeriq.{table} FOR EACH ROW EXECUTE FUNCTION playeriq.guard_roster_association()"
        )


def downgrade() -> None:
    # Never erase unclaimed athletes by forcing NULL ownership into a fake account.
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM playeriq.players WHERE owner_user_id IS NULL) THEN "
        "RAISE EXCEPTION 'Resolve unclaimed roster data before downgrade'; END IF; END $$"
    )
    for table in ("player_sessions", "player_source_identities"):
        op.execute(f"DROP TRIGGER guard_roster_association ON playeriq.{table}")
        op.execute(f"REVOKE UPDATE (player_id) ON playeriq.{table} FROM playeriq_api")
    op.execute("DROP FUNCTION playeriq.guard_roster_association()")
    for table, names in {
        "players": ("players_unclaimed_select", "players_unclaimed_insert", "players_resolution_update"),
        "player_sessions": ("sessions_roster_insert", "player_sessions_resolution_update"),
        "player_source_identities": ("identities_roster_insert", "player_source_identities_resolution_update"),
    }.items():
        for name in names:
            op.execute(f"DROP POLICY {name} ON playeriq.{table}")
    op.execute("REVOKE UPDATE (archived_at) ON playeriq.players FROM playeriq_api")
    op.execute("DROP POLICY team_roster_resolution_update ON playeriq.team_roster")
    op.drop_table("team_roster_resolutions", schema="playeriq")
    op.drop_table("team_report_import_rows", schema="playeriq")
    op.drop_table("team_report_imports", schema="playeriq")
    op.drop_table("team_roster", schema="playeriq")
    op.execute("DROP FUNCTION playeriq.is_roster_player(uuid,uuid)")
    op.drop_constraint("ck_players_player_origin", "players", schema="playeriq")
    op.drop_index("ix_players_origin_team", "players", schema="playeriq")
    op.drop_column("players", "origin_team_id", schema="playeriq")
    op.alter_column("players", "owner_user_id", nullable=False, schema="playeriq")
