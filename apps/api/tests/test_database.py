from uuid import uuid4

import app.models  # noqa: F401
import pytest
from app.db.base import Base
from app.ingestion.service import IngestionService
from app.models.tables import (
    ActivityReport,
    IngestionFinding,
    PlayerSession,
    ReportUpload,
    SourceAthleteRow,
    SourceMetricObservation,
)
from app.repositories.ingestion import persist_inspection
from app.repositories.uploads import content_sha256, find_active_duplicate
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


@pytest.fixture
def db_session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        execution_options={"schema_translate_map": {"auth": None, "playeriq": None}},
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def _upload(user_id, digest: str, status: str = "received") -> ReportUpload:
    return ReportUpload(
        uploaded_by_user_id=user_id,
        storage_key=f"private/{uuid4()}.pdf",
        original_filename="synthetic.pdf",
        mime_type="application/pdf",
        byte_size=1000,
        sha256=digest,
        status=status,
    )


def test_models_have_private_schema_and_expected_constraints() -> None:
    assert len([table for table in Base.metadata.tables.values() if table.schema == "playeriq"]) == 19
    assert "playeriq.ai_provider_requests" in Base.metadata.tables
    assert Base.metadata.tables["auth.users"].info["external"] is True
    assert SourceAthleteRow.__table__.schema == "playeriq"
    assert PlayerSession.__table__.columns["source_athlete_row_id"].unique


def test_persistence_keeps_raw_scope_and_does_not_link_players(db_session: Session, synthetic_pdf: bytes) -> None:
    inspection = IngestionService().inspect_pdf(synthetic_pdf)
    upload = _upload(uuid4(), content_sha256(synthetic_pdf))
    db_session.add(upload)
    db_session.flush()
    persist_inspection(db_session, upload, inspection)
    db_session.flush()
    assert upload.status == "awaiting_link"
    assert db_session.scalar(select(func.count()).select_from(ActivityReport)) == 1
    assert db_session.scalar(select(func.count()).select_from(SourceAthleteRow)) == 12
    assert db_session.scalar(select(func.count()).select_from(SourceMetricObservation)) == 141
    assert db_session.scalar(select(func.count()).select_from(PlayerSession)) == 0
    assert db_session.scalar(select(func.count()).select_from(IngestionFinding)) > 0
    assert (
        db_session.scalar(
            select(func.count()).select_from(SourceMetricObservation).where(SourceMetricObservation.scope == "report")
        )
        == 9
    )
    assert (
        db_session.scalar(
            select(SourceMetricObservation.raw_value).where(
                SourceMetricObservation.source_label == "Overall (%)",
                SourceMetricObservation.scope == "athlete",
                SourceMetricObservation.raw_value == "1550",
            )
        )
        == "1550"
    )
    with pytest.raises(ValueError, match="already been persisted"):
        persist_inspection(db_session, upload, inspection)


def test_duplicate_detection_is_user_scoped_and_ignores_deleted(db_session: Session) -> None:
    one, two = uuid4(), uuid4()
    digest = content_sha256(b"synthetic bytes")
    active = _upload(one, digest)
    db_session.add(active)
    db_session.add(_upload(two, digest))
    db_session.flush()
    assert find_active_duplicate(db_session, one, digest) is active
    assert find_active_duplicate(db_session, uuid4(), digest) is None
    active.status = "deleted"
    db_session.flush()
    assert find_active_duplicate(db_session, one, digest) is None
    with pytest.raises(ValueError, match="SHA-256"):
        find_active_duplicate(db_session, one, "bad")


def test_upload_size_check_constraint(db_session: Session) -> None:
    upload = _upload(uuid4(), content_sha256(b"bad"))
    upload.byte_size = -1
    db_session.add(upload)
    with pytest.raises(IntegrityError):
        db_session.flush()
