# PlayerIQ

PlayerIQ is a football GPS performance platform. Phases 1–3 provide an authenticated backend path from a supported text PDF to explicitly linked player sessions, uploader-confirmed chart labels, and deterministic historical analytics. Committed tests generate a synthetic report in memory. The frontend and AI Analyst are later phases.

Architecture and source data decisions: [SPEC.md](docs/SPEC.md), [GPS_DATA_MODEL.md](docs/GPS_DATA_MODEL.md), [INGESTION.md](docs/INGESTION.md), and [AUTH.md](docs/AUTH.md).

## Development setup

Use Python 3.12 and a **development** Supabase project. Keep the project URL, database passwords, and server-only Storage key in an ignored `.env`; `.env.example` contains placeholders. Use separate restricted PostgreSQL login roles for the API and worker as described in [AUTH.md](docs/AUTH.md). Do not use `postgres`, `service_role`, a superuser, or a role with `BYPASSRLS` as a runtime login. Apply migrations with a separate privileged migration connection. Configure a private Storage bucket named `playeriq-reports` (or set `SUPABASE_STORAGE_BUCKET`), with public access disabled. Never expose the Storage secret key to a browser.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-lock.txt
python -m pip install -e . --no-deps
Copy-Item .env.example .env
# Set DATABASE_URL in .env to the privileged development migration connection.
$env:PYTHONPATH = "apps/api"
python -m alembic upgrade head
python -m alembic current
# Create the restricted login roles as described in docs/AUTH.md.
# Replace DATABASE_URL with the restricted API connection; set the worker and Storage values.
python -m uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port 8000
```

`DATABASE_URL` must use a login with membership in `playeriq_api`; `WORKER_DATABASE_URL` must use a different login with membership in `playeriq_worker`. PostgreSQL URLs beginning `postgres://` or `postgresql://` are normalized to psycopg. Supabase transaction-pooler connections on port 6543 disable psycopg prepared statements. TLS is required for `*.supabase.com` hosts. `SUPABASE_URL` and `SUPABASE_JWT_AUDIENCE` configure access-token verification through the project's asymmetric JWKS. `SUPABASE_STORAGE_SECRET_KEY` stays server-side. `MAX_UPLOAD_BYTES` defaults to 10 MiB; `JWKS_CACHE_SECONDS`, validation thresholds, CORS origins, and log level have safe defaults in `.env.example`.

The command above uses `DATABASE_URL` for the privileged **migration** connection first. Migration `0003` creates the NOLOGIN group roles, and `0004` secures Alembic's version table; create distinct restricted login roles and grant membership afterward, then restore `DATABASE_URL` to the API login before starting FastAPI. Migrations refer to the Supabase-owned `auth.users` table; they do not create or alter it. No reset command is required. When using a Supabase pooler, use the supplied connection string and correct pooler mode. See [AUTH.md](docs/AUTH.md) for exact SQL and security checks.

`GET /healthz` reports process health. `GET /readyz` probes the database and verifies that the login is a restricted API-role member; it returns 503 when the database is unconfigured or unavailable.

## Ingestion worker

The API queues a durable job after a private upload. Run the deterministic worker command from another terminal or schedule it on the backend host:

```powershell
$env:PYTHONPATH = "apps/api"
python -m app.cli.process_ingestion --limit 20
```

Run it repeatedly to process subsequent jobs. It claims due jobs with `FOR UPDATE SKIP LOCKED`, retries transient storage/processing failures, and leaves the report in `awaiting_link` for explicit review. The worker uses `WORKER_DATABASE_URL` and the same private Storage configuration as the API. It has no public trigger endpoint.

## Current API

All `/v1` routes require `Authorization: Bearer <Supabase access token>`:

| Route | Purpose |
| --- | --- |
| `GET /v1/me`, `PATCH /v1/me` | Read or create/update the user's profile. |
| `POST /v1/players`, `GET /v1/players`, `GET /v1/players/{player_id}` | Create and read authorized player profiles. |
| `POST /v1/report-uploads` | Upload a supported multipart PDF and queue ingestion. |
| `GET /v1/report-uploads/{upload_id}` | Uploader-only status, findings, and candidate athlete rows. |
| `GET /v1/report-uploads/{upload_id}/chart-reviews` | Uploader-only chart proposal/review history. |
| `POST /v1/report-uploads/{upload_id}/chart-reviews` | Propose an exact printed page-2 `Player Load` or `Maximum Velocity` label for a selected source row UUID. |
| `POST /v1/report-uploads/{upload_id}/chart-reviews/{review_id}/confirm` | Confirm the proposed label and athlete match; keep anomalous speed held. |
| `POST /v1/report-uploads/{upload_id}/links` | Explicitly link one eligible row to the uploader's own player profile. |
| `GET /v1/report-uploads/{upload_id}/file` | Uploader-only private report download. |
| `GET /v1/players/{player_id}/sessions` | Authorized, paginated accepted sessions. |
| `GET /v1/players/{player_id}/sessions/{session_id}` | Authorized session metrics and source provenance. |
| `GET /v1/players/{player_id}/analytics/overview` | Versioned latest comparisons, top-speed record, highest-distance training session, and changes. |
| `GET /v1/players/{player_id}/analytics/trend?metric=&from=&to=&type=` | Accepted-value points, change, and eligible weekly slope. |
| `GET /v1/players/{player_id}/analytics/outliers?type=&limit=` | Median/MAD workload results with source session IDs. |

Only the reviewed Activity Report text-PDF layout is supported. Candidate rows do not become sessions by name matching. Chart labels require manual transcription and uploader confirmation against the page-2 PDF chart; no OCR or bar-height estimation runs. The exact human-confirmed label becomes authoritative. A confirmed post-link correction updates the accepted metric and changes the player-history fingerprint. Speed readings above the configured review value stay held. `Player Load` is a source index of unknown definition, so its history is stored but cross-session comparisons are `not_comparable` until a verified definition/configuration is available. Zero-recorded and review-needed rows are held. The analytics domain is pure and shared by HTTP and future AI tools; every result carries `analytics_v1`. Coach invitations and coach writes are deferred; coach read grants already have a structural authorization path, but no invitation endpoint is present.

## Tests and privacy

```powershell
python -m pytest -q
python -m ruff check apps/api db/migrations
python -m ruff format --check apps/api db/migrations
python -m mypy apps/api/app
```

Unit/API tests use generated keys, fabricated users, an in-memory fake Storage service, SQLite integration, and a synthetic PDF. Optional read-only development Supabase checks are described in [AUTH.md](docs/AUTH.md) and are disabled by default. The optional private-report test uses `PLAYERIQ_LOCAL_REPORT` only when explicitly set and never commits report data. `sample-data/` remains ignored except for its README.
