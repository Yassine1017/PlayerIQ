"""Persist structured extraction and validation findings.

Revision ID: 0002_ingestion_findings
Revises: 0001_initial
"""

from alembic import op

revision = "0002_ingestion_findings"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE playeriq.ingestion_findings (
            id UUID PRIMARY KEY,
            report_upload_id UUID NOT NULL REFERENCES playeriq.report_uploads(id),
            code VARCHAR(100) NOT NULL,
            message TEXT NOT NULL,
            severity VARCHAR(12) NOT NULL,
            scope VARCHAR(12) NOT NULL,
            row_ordinal INTEGER,
            metric_key VARCHAR(100),
            source_locator VARCHAR(255),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX ix_ingestion_findings_upload_row
        ON playeriq.ingestion_findings (report_upload_id, row_ordinal)
    """)
    op.execute("ALTER TABLE playeriq.ingestion_findings ENABLE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON playeriq.ingestion_findings FROM PUBLIC")


def downgrade() -> None:
    op.execute("DROP TABLE playeriq.ingestion_findings")
