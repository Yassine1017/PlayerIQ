"""Grounded AI persistence and creator-private access.

Revision ID: 0006_ai_analyst
Revises: 0005_chart_metric_reviews
"""

from alembic import op

revision = "0006_ai_analyst"
down_revision = "0005_chart_metric_reviews"
branch_labels = None
depends_on = None

ACTOR = "nullif(current_setting('playeriq.current_user_id', true), '')::uuid"
ACCESS = f"""EXISTS (
  SELECT 1 FROM playeriq.players p WHERE p.id = player_id AND p.archived_at IS NULL
  AND (p.owner_user_id = {ACTOR} OR EXISTS (
    SELECT 1 FROM playeriq.player_coaches pc WHERE pc.player_id = p.id
    AND pc.coach_user_id = {ACTOR} AND pc.revoked_at IS NULL)))"""
RUN_ACCESS = f"actor_user_id = {ACTOR} AND {ACCESS}"
THREAD_ACCESS = f"created_by_user_id = {ACTOR} AND {ACCESS}"
MESSAGE_ACCESS = f"""EXISTS (
  SELECT 1 FROM playeriq.chat_threads t JOIN playeriq.players p ON p.id = t.player_id
  WHERE t.id = thread_id AND t.created_by_user_id = {ACTOR} AND p.archived_at IS NULL
  AND (p.owner_user_id = {ACTOR} OR EXISTS (
    SELECT 1 FROM playeriq.player_coaches pc WHERE pc.player_id = p.id
    AND pc.coach_user_id = {ACTOR} AND pc.revoked_at IS NULL)))"""
TOOL_ACCESS = f"""EXISTS (SELECT 1 FROM playeriq.ai_runs r
  WHERE r.id = ai_run_id AND r.actor_user_id = {ACTOR})"""


def upgrade() -> None:
    op.execute(
        "ALTER TABLE playeriq.ai_runs ADD COLUMN analytics_rule_version varchar(40) NOT NULL DEFAULT 'analytics_v1'"
    )
    op.execute("ALTER TABLE playeriq.ai_runs ADD COLUMN idempotency_key uuid")
    op.execute("ALTER TABLE playeriq.ai_runs ADD COLUMN provider varchar(40) NOT NULL DEFAULT 'openai'")
    op.execute(
        "ALTER TABLE playeriq.ai_runs ADD CONSTRAINT uq_ai_runs_actor_player_idempotency UNIQUE (actor_user_id, player_id, idempotency_key)"
    )
    op.execute("CREATE INDEX ix_ai_runs_actor_created ON playeriq.ai_runs (actor_user_id, created_at)")
    op.execute("GRANT SELECT, INSERT, UPDATE ON playeriq.ai_runs TO playeriq_api")
    op.execute("GRANT SELECT, INSERT ON playeriq.ai_tool_calls TO playeriq_api")
    op.execute("GRANT SELECT, INSERT ON playeriq.chat_threads TO playeriq_api")
    op.execute("GRANT SELECT, INSERT ON playeriq.chat_messages TO playeriq_api")
    for name, table, action, expression in (
        ("ai_runs_actor_select", "ai_runs", "SELECT", RUN_ACCESS),
        ("ai_runs_actor_insert", "ai_runs", "INSERT", RUN_ACCESS),
        ("ai_runs_actor_update", "ai_runs", "UPDATE", RUN_ACCESS),
        ("chat_threads_creator_select", "chat_threads", "SELECT", THREAD_ACCESS),
        ("chat_threads_creator_insert", "chat_threads", "INSERT", THREAD_ACCESS),
        ("chat_messages_creator_select", "chat_messages", "SELECT", MESSAGE_ACCESS),
        ("chat_messages_creator_insert", "chat_messages", "INSERT", MESSAGE_ACCESS),
        ("ai_tool_calls_actor_select", "ai_tool_calls", "SELECT", TOOL_ACCESS),
        ("ai_tool_calls_actor_insert", "ai_tool_calls", "INSERT", TOOL_ACCESS),
    ):
        sql = f"CREATE POLICY {name} ON playeriq.{table} FOR {action} TO playeriq_api"
        if action != "INSERT":
            sql += f" USING ({expression})"
        if action in ("INSERT", "UPDATE"):
            sql += f" WITH CHECK ({expression})"
        op.execute(sql)


def downgrade() -> None:
    for table, names in (
        ("ai_runs", ("ai_runs_actor_select", "ai_runs_actor_insert", "ai_runs_actor_update")),
        ("chat_threads", ("chat_threads_creator_select", "chat_threads_creator_insert")),
        ("chat_messages", ("chat_messages_creator_select", "chat_messages_creator_insert")),
        ("ai_tool_calls", ("ai_tool_calls_actor_select", "ai_tool_calls_actor_insert")),
    ):
        for name in names:
            op.execute(f"DROP POLICY {name} ON playeriq.{table}")
    op.execute(
        "REVOKE ALL ON playeriq.ai_runs, playeriq.ai_tool_calls, playeriq.chat_threads, playeriq.chat_messages FROM playeriq_api"
    )
    op.execute("DROP INDEX playeriq.ix_ai_runs_actor_created")
    op.execute("ALTER TABLE playeriq.ai_runs DROP CONSTRAINT uq_ai_runs_actor_player_idempotency")
    op.execute("ALTER TABLE playeriq.ai_runs DROP COLUMN idempotency_key")
    op.execute("ALTER TABLE playeriq.ai_runs DROP COLUMN provider")
    op.execute("ALTER TABLE playeriq.ai_runs DROP COLUMN analytics_rule_version")
