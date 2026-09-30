"""Retain sub-microdollar cost precision for small provider requests.

Revision ID: 0008_ai_budget_precision
Revises: 0007_global_ai_budget
"""

from alembic import op

revision = "0008_ai_budget_precision"
down_revision = "0007_global_ai_budget"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE playeriq.ai_provider_requests ALTER COLUMN reserved_cost_usd TYPE numeric(18,9)")
    op.execute("ALTER TABLE playeriq.ai_provider_requests ALTER COLUMN estimated_cost_usd TYPE numeric(18,9)")


def downgrade() -> None:
    op.execute("ALTER TABLE playeriq.ai_provider_requests ALTER COLUMN reserved_cost_usd TYPE numeric(12,6)")
    op.execute("ALTER TABLE playeriq.ai_provider_requests ALTER COLUMN estimated_cost_usd TYPE numeric(12,6)")
