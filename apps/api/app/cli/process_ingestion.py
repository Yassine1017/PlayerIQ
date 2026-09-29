"""Process queued reports without exposing a public job-trigger endpoint."""

import argparse

from app.core.config import get_settings
from app.db.session import Database, make_engine
from app.services.jobs import process_next_job
from app.services.storage import SupabaseReportStorage


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
    try:
        for _ in range(args.limit):
            if not process_next_job(database, storage, settings):
                break
    finally:
        database.engine.dispose()


if __name__ == "__main__":
    main()
