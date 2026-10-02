"""Process queued reports and legacy chart backfills within a bounded pass."""

import argparse
import logging

from app.core.config import get_settings
from app.db.session import Database, make_engine
from app.services.chart_backfill import process_next_chart_backfill
from app.services.jobs import process_next_job
from app.services.storage import SupabaseReportStorage
from app.services.team_imports import process_next_team_import


def main() -> None:
    parser = argparse.ArgumentParser(description="Process PlayerIQ GPS ingestion jobs")
    parser.add_argument("--limit", type=int, default=1, help="Maximum jobs to process in this run")
    args = parser.parse_args()
    if not 1 <= args.limit <= 100:
        parser.error("--limit must be between 1 and 100")
    settings = get_settings()
    if not settings.worker_database_url:
        parser.error("WORKER_DATABASE_URL must name the restricted worker database role")
    database = Database(make_engine(settings.worker_database_url), expected_role="playeriq_worker")
    storage = SupabaseReportStorage(settings)
    api_database = Database(make_engine(settings.database_url)) if settings.database_url else None
    try:
        for _ in range(args.limit):
            if not process_next_job(database, storage, settings):
                if api_database is None:
                    break
                if process_next_team_import(database, api_database, settings):
                    continue
                if not process_next_chart_backfill(database, api_database, storage, settings):
                    break
    except Exception as exc:
        logging.getLogger(__name__).error("ingestion_worker_failed error_type=%s", type(exc).__name__)
        raise SystemExit(1) from None
    finally:
        database.engine.dispose()
        if api_database is not None:
            api_database.engine.dispose()


if __name__ == "__main__":
    main()
