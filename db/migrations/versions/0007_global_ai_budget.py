"""Serialize a global monthly AI budget and persist each provider request.

Revision ID: 0007_global_ai_budget
Revises: 0006_ai_analyst
"""

import sqlalchemy as sa
from alembic import op

revision = "0007_global_ai_budget"
down_revision = "0006_ai_analyst"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_provider_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("ai_run_id", sa.Uuid(), sa.ForeignKey("playeriq.ai_runs.id"), nullable=False),
        sa.Column("budget_month", sa.Date(), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("pricing_version", sa.String(80), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("reserved_cost_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column("estimated_cost_usd", sa.Numeric(12, 6)),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('reserved','completed','uncertain','unknown_pricing')", name="status"),
        sa.CheckConstraint("reserved_cost_usd >= 0", name="reserved_cost_nonnegative"),
        sa.CheckConstraint("estimated_cost_usd IS NULL OR estimated_cost_usd >= 0", name="estimated_cost_nonnegative"),
        schema="playeriq",
    )
    op.create_index(
        "ix_ai_provider_requests_month", "ai_provider_requests", ["budget_month", "created_at"], schema="playeriq"
    )
    op.execute("ALTER TABLE playeriq.ai_provider_requests ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE playeriq.ai_provider_requests FORCE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON playeriq.ai_provider_requests FROM PUBLIC, anon, authenticated, playeriq_api")
    # Phase 5 stored only run totals. Preserve known historical usage once as a
    # legacy request; unknown model pricing blocks future reservations that month.
    op.execute("""
        INSERT INTO playeriq.ai_provider_requests
          (id, ai_run_id, budget_month, model, pricing_version, status,
           reserved_cost_usd, estimated_cost_usd, input_tokens, output_tokens,
           created_at, completed_at)
        SELECT gen_random_uuid(), r.id,
          date_trunc('month', coalesce(r.completed_at, r.created_at) AT TIME ZONE 'UTC')::date,
          r.model,
          CASE WHEN r.model = 'gpt-6-luna' THEN 'gpt-6-luna-2026-09-30' ELSE 'unknown' END,
          CASE WHEN r.model <> 'gpt-6-luna' THEN 'unknown_pricing'
               WHEN r.input_tokens IS NULL OR r.output_tokens IS NULL THEN 'uncertain'
               ELSE 'completed' END,
          CASE WHEN r.input_tokens IS NULL OR r.output_tokens IS NULL THEN 0.010000 ELSE 0 END,
          CASE WHEN r.model = 'gpt-6-luna' AND r.input_tokens IS NOT NULL AND r.output_tokens IS NOT NULL
               THEN round((r.input_tokens * 0.10 + r.output_tokens * 0.50) / 1000000, 6)
               ELSE NULL END,
          r.input_tokens, r.output_tokens, r.created_at, r.completed_at
        FROM playeriq.ai_runs r
        WHERE r.provider = 'openai' AND (r.input_tokens IS NOT NULL OR r.output_tokens IS NOT NULL)
    """)
    op.execute("""
        CREATE FUNCTION playeriq.ai_budget_summary(p_month date)
        RETURNS TABLE(spend numeric, request_count bigint, input_tokens bigint,
                      output_tokens bigint, unknown_pricing boolean)
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
        BEGIN
          IF nullif(current_setting('playeriq.current_user_id', true), '') IS NULL THEN
            RAISE EXCEPTION 'AI budget actor context required';
          END IF;
          RETURN QUERY SELECT
            coalesce(sum(CASE WHEN q.status IN ('reserved','uncertain') THEN q.reserved_cost_usd
                              ELSE coalesce(q.estimated_cost_usd, 0) END), 0),
            count(*), coalesce(sum(q.input_tokens), 0), coalesce(sum(q.output_tokens), 0),
            coalesce(bool_or(q.status = 'unknown_pricing'), false)
          FROM playeriq.ai_provider_requests q WHERE q.budget_month = p_month;
        END $$
    """)
    op.execute("""
        CREATE FUNCTION playeriq.ai_budget_reserve(
          p_run uuid, p_model text, p_price_version text, p_hold numeric, p_limit numeric)
        RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
        DECLARE v_actor uuid; v_month date; v_spend numeric; v_unknown boolean; v_id uuid;
        BEGIN
          v_actor := nullif(current_setting('playeriq.current_user_id', true), '')::uuid;
          IF v_actor IS NULL OR NOT EXISTS (
            SELECT 1 FROM playeriq.ai_runs r JOIN playeriq.players p ON p.id = r.player_id
            WHERE r.id = p_run AND r.actor_user_id = v_actor AND r.provider = 'openai'
              AND r.model = p_model AND r.status = 'pending' AND p.archived_at IS NULL
              AND (p.owner_user_id = v_actor OR EXISTS (
                SELECT 1 FROM playeriq.player_coaches pc WHERE pc.player_id = p.id
                AND pc.coach_user_id = v_actor AND pc.revoked_at IS NULL))) THEN
            RAISE EXCEPTION 'AI budget reservation access denied';
          END IF;
          IF p_hold <= 0 OR p_limit <= 0 OR p_price_version = '' THEN
            RAISE EXCEPTION 'Invalid AI budget configuration';
          END IF;
          PERFORM pg_advisory_xact_lock(65315, 1);
          v_month := date_trunc('month', clock_timestamp() AT TIME ZONE 'UTC')::date;
          SELECT s.spend, s.unknown_pricing INTO v_spend, v_unknown
            FROM playeriq.ai_budget_summary(v_month) s;
          IF v_unknown OR v_spend + p_hold > p_limit THEN RETURN NULL; END IF;
          v_id := gen_random_uuid();
          INSERT INTO playeriq.ai_provider_requests
            (id, ai_run_id, budget_month, model, pricing_version, status, reserved_cost_usd)
          VALUES (v_id, p_run, v_month, p_model, p_price_version, 'reserved', p_hold);
          RETURN v_id;
        END $$
    """)
    op.execute("""
        CREATE FUNCTION playeriq.ai_budget_settle(
          p_request uuid, p_model text, p_inputs integer, p_outputs integer, p_cost numeric)
        RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
        DECLARE v_actor uuid;
        BEGIN
          v_actor := nullif(current_setting('playeriq.current_user_id', true), '')::uuid;
          IF v_actor IS NULL OR (p_cost IS NULL) <> (p_inputs IS NULL OR p_outputs IS NULL)
             OR coalesce(p_inputs, 0) < 0 OR coalesce(p_outputs, 0) < 0 OR coalesce(p_cost, 0) < 0 THEN
            RAISE EXCEPTION 'Invalid AI budget settlement';
          END IF;
          UPDATE playeriq.ai_provider_requests q SET
            status = CASE WHEN p_cost IS NULL THEN 'uncertain' ELSE 'completed' END,
            input_tokens = p_inputs, output_tokens = p_outputs,
            estimated_cost_usd = p_cost, completed_at = clock_timestamp()
          FROM playeriq.ai_runs r
          WHERE q.id = p_request AND q.ai_run_id = r.id AND q.model = p_model
            AND q.status = 'reserved' AND r.actor_user_id = v_actor;
          IF NOT FOUND THEN RAISE EXCEPTION 'AI budget settlement access denied'; END IF;
        END $$
    """)
    for signature in (
        "ai_budget_summary(date)",
        "ai_budget_reserve(uuid,text,text,numeric,numeric)",
        "ai_budget_settle(uuid,text,integer,integer,numeric)",
    ):
        op.execute(f"REVOKE ALL ON FUNCTION playeriq.{signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION playeriq.{signature} TO playeriq_api")


def downgrade() -> None:
    for signature in (
        "ai_budget_settle(uuid,text,integer,integer,numeric)",
        "ai_budget_reserve(uuid,text,text,numeric,numeric)",
        "ai_budget_summary(date)",
    ):
        op.execute(f"DROP FUNCTION playeriq.{signature}")
    op.drop_index("ix_ai_provider_requests_month", table_name="ai_provider_requests", schema="playeriq")
    op.drop_table("ai_provider_requests", schema="playeriq")
