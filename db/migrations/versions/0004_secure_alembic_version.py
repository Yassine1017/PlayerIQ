"""Remove Supabase Data API grants from Alembic's public version table.

Revision ID: 0004_secure_alembic_version
Revises: 0003_phase2_access
"""

from alembic import op

revision = "0004_secure_alembic_version"
down_revision = "0003_phase2_access"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("REVOKE ALL ON TABLE public.alembic_version FROM PUBLIC, anon, authenticated, service_role")
    op.execute("ALTER TABLE public.alembic_version ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    # Leave grants revoked. Disabling RLS is safe only because the table stays
    # inaccessible to Data API roles; a future migration can re-enable it.
    op.execute("ALTER TABLE public.alembic_version DISABLE ROW LEVEL SECURITY")
