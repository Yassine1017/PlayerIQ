"""Audited chart-label review and restricted post-link metric updates.

Revision ID: 0005_chart_metric_reviews
Revises: 0004_secure_alembic_version
"""

import sqlalchemy as sa
from alembic import op

revision = "0005_chart_metric_reviews"
down_revision = "0004_secure_alembic_version"
branch_labels = None
depends_on = None

ACTOR = "nullif(current_setting('playeriq.current_user_id', true), '')::uuid"
ROW_OWNER = f"""EXISTS (
    SELECT 1 FROM playeriq.source_athlete_rows r
    JOIN playeriq.report_uploads u ON u.id = r.report_upload_id
    WHERE r.id = athlete_row_id AND u.uploaded_by_user_id = {ACTOR}
)"""
SESSION_ACCESS = f"""metric_key IN ('maximum_velocity_kmh','player_load_reported') AND EXISTS (
    SELECT 1 FROM playeriq.player_sessions s
    JOIN playeriq.source_athlete_rows r ON r.id = s.source_athlete_row_id
    JOIN playeriq.report_uploads u ON u.id = r.report_upload_id
    WHERE s.id = player_session_id AND u.uploaded_by_user_id = {ACTOR}
)"""


def upgrade() -> None:
    op.create_table(
        "chart_metric_reviews",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("athlete_row_id", sa.Uuid(), sa.ForeignKey("playeriq.source_athlete_rows.id"), nullable=False),
        sa.Column("metric_key", sa.String(100), nullable=False),
        sa.Column("raw_label", sa.String(120), nullable=False),
        sa.Column("parsed_value", sa.Numeric(12, 3), nullable=False),
        sa.Column("source_locator", sa.String(255), nullable=False),
        sa.Column("capture_method", sa.String(24), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("proposed_by_user_id", sa.Uuid(), sa.ForeignKey("auth.users.id"), nullable=False),
        sa.Column("reviewed_by_user_id", sa.Uuid(), sa.ForeignKey("auth.users.id")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("review_reason", sa.String(500)),
        sa.Column(
            "source_observation_id",
            sa.Uuid(),
            sa.ForeignKey("playeriq.source_metric_observations.id"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("metric_key IN ('maximum_velocity_kmh','player_load_reported')", name="chart_metric_key"),
        sa.CheckConstraint("status IN ('proposed','confirmed','held','superseded')", name="chart_review_status"),
        sa.CheckConstraint("parsed_value >= 0", name="chart_review_nonnegative"),
        schema="playeriq",
    )
    op.create_index(
        "ix_chart_review_row_metric",
        "chart_metric_reviews",
        ["athlete_row_id", "metric_key", "created_at"],
        schema="playeriq",
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_chart_review_active ON playeriq.chart_metric_reviews "
        "(athlete_row_id, metric_key) WHERE status = 'confirmed'"
    )
    op.execute("ALTER TABLE playeriq.chart_metric_reviews ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE playeriq.chart_metric_reviews FORCE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON playeriq.chart_metric_reviews FROM PUBLIC, anon, authenticated")
    op.execute("GRANT SELECT, INSERT, UPDATE ON playeriq.chart_metric_reviews TO playeriq_api")
    op.execute("GRANT INSERT ON playeriq.source_metric_observations TO playeriq_api")
    op.execute("GRANT UPDATE, DELETE ON playeriq.session_metric_values TO playeriq_api")
    op.execute(
        "CREATE POLICY chart_reviews_owner_select ON playeriq.chart_metric_reviews "
        f"FOR SELECT TO playeriq_api USING ({ROW_OWNER})"
    )
    op.execute(
        "CREATE POLICY chart_reviews_owner_insert ON playeriq.chart_metric_reviews "
        f"FOR INSERT TO playeriq_api WITH CHECK ({ROW_OWNER} AND proposed_by_user_id = {ACTOR})"
    )
    op.execute(
        "CREATE POLICY chart_reviews_owner_update ON playeriq.chart_metric_reviews "
        f"FOR UPDATE TO playeriq_api USING ({ROW_OWNER}) "
        f"WITH CHECK ({ROW_OWNER} AND proposed_by_user_id = {ACTOR} "
        f"AND (reviewed_by_user_id IS NULL OR reviewed_by_user_id = {ACTOR}))"
    )
    op.execute(
        "CREATE POLICY source_metrics_owner_insert ON playeriq.source_metric_observations "
        "FOR INSERT TO playeriq_api WITH CHECK (scope = 'athlete' AND "
        f"EXISTS (SELECT 1 FROM playeriq.source_athlete_rows r JOIN playeriq.report_uploads u "
        f"ON u.id = r.report_upload_id WHERE r.id = athlete_row_id AND u.uploaded_by_user_id = {ACTOR}))"
    )
    op.execute(
        "CREATE POLICY session_metrics_access_update ON playeriq.session_metric_values "
        f"FOR UPDATE TO playeriq_api USING ({SESSION_ACCESS}) WITH CHECK ({SESSION_ACCESS})"
    )
    op.execute(
        "CREATE POLICY session_metrics_access_delete ON playeriq.session_metric_values "
        f"FOR DELETE TO playeriq_api USING ({SESSION_ACCESS})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS session_metrics_access_delete ON playeriq.session_metric_values")
    op.execute("DROP POLICY IF EXISTS session_metrics_access_update ON playeriq.session_metric_values")
    op.execute("DROP POLICY IF EXISTS source_metrics_owner_insert ON playeriq.source_metric_observations")
    op.execute("DROP POLICY IF EXISTS chart_reviews_owner_update ON playeriq.chart_metric_reviews")
    op.execute("DROP POLICY IF EXISTS chart_reviews_owner_insert ON playeriq.chart_metric_reviews")
    op.execute("DROP POLICY IF EXISTS chart_reviews_owner_select ON playeriq.chart_metric_reviews")
    op.execute("REVOKE UPDATE, DELETE ON playeriq.session_metric_values FROM playeriq_api")
    op.execute("REVOKE INSERT ON playeriq.source_metric_observations FROM playeriq_api")
    op.execute("REVOKE ALL ON playeriq.chart_metric_reviews FROM playeriq_api")
    op.execute("DROP INDEX IF EXISTS playeriq.uq_chart_review_active")
    op.drop_index("ix_chart_review_row_metric", table_name="chart_metric_reviews", schema="playeriq")
    op.drop_table("chart_metric_reviews", schema="playeriq")
