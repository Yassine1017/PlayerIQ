"""Break team insert-policy recursion without bypassing row security.

Revision ID: 0010_team_creation_rls
Revises: 0009_player_identity_teams
"""

from alembic import op

revision = "0010_team_creation_rls"
down_revision = "0009_player_identity_teams"
branch_labels = None
depends_on = None

ACTOR = "nullif(current_setting('playeriq.current_user_id', true), '')::uuid"

CREATOR_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION playeriq.is_team_creator(p_team_id uuid)
RETURNS boolean
LANGUAGE plpgsql STABLE SECURITY INVOKER
SET search_path = pg_catalog
AS $body$
BEGIN
  RETURN EXISTS (
    SELECT 1 FROM playeriq.teams AS t
    WHERE t.id = p_team_id
      AND t.created_by_user_id = nullif(current_setting('playeriq.current_user_id', true), '')::uuid
  );
END;
$body$
"""


def upgrade() -> None:
    # Direct subqueries make INSERT membership -> SELECT teams -> SELECT
    # membership recurse during PostgreSQL's RLS rewrite. A non-inlineable
    # PL/pgSQL call plans the SELECT separately: SELECT policies remain acyclic.
    # SECURITY INVOKER is deliberate: no elevated owner or RLS bypass is needed.
    op.execute(CREATOR_FUNCTION_SQL)
    op.execute(
        "REVOKE ALL ON FUNCTION playeriq.is_team_creator(uuid) FROM PUBLIC, anon, authenticated, playeriq_worker"
    )
    op.execute("GRANT EXECUTE ON FUNCTION playeriq.is_team_creator(uuid) TO playeriq_api")
    for table in ("team_memberships", "team_manager_grants"):
        op.execute(
            f"ALTER POLICY {table}_creator_insert ON playeriq.{table} WITH CHECK (playeriq.is_team_creator(team_id))"
        )


def downgrade() -> None:
    for table in ("team_memberships", "team_manager_grants"):
        op.execute(
            f"ALTER POLICY {table}_creator_insert ON playeriq.{table} "
            f"WITH CHECK (EXISTS (SELECT 1 FROM playeriq.teams t "
            f"WHERE t.id = playeriq.{table}.team_id AND t.created_by_user_id = {ACTOR}))"
        )
    op.execute("DROP FUNCTION playeriq.is_team_creator(uuid)")
