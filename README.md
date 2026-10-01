# PlayerIQ

PlayerIQ is a football GPS performance platform. Phases 1–5.2 provide an authenticated path from a supported PDF to explicitly linked player sessions, automatic capture of printed chart labels where reliable, uploader review when needed, deterministic historical analytics, a responsive Next.js web application, and a grounded AI Analyst. Committed tests use synthetic data.

Architecture and source data decisions: [SPEC.md](docs/SPEC.md), [GPS_DATA_MODEL.md](docs/GPS_DATA_MODEL.md), [INGESTION.md](docs/INGESTION.md), [AUTH.md](docs/AUTH.md), and [AI_ANALYST.md](docs/AI_ANALYST.md).

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

## Frontend setup

The Next.js app is in `apps/web`. It uses Supabase Auth in the browser and sends its access token to FastAPI. Set **only public values** in an ignored `apps/web/.env.local` (copy `apps/web/.env.example`):

| Frontend variable | Purpose |
| --- | --- |
| `NEXT_PUBLIC_SUPABASE_URL` | URL of the **PlayerIQ Dev** Supabase project for local development. |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | Enabled public publishable key from that same project. |
| `NEXT_PUBLIC_API_URL` | Browser-reachable FastAPI origin, normally `http://localhost:8000`. |

These variables are deliberately browser-visible. `DATABASE_URL`, `WORKER_DATABASE_URL`, `SUPABASE_STORAGE_SECRET_KEY`, and all database credentials remain **server-only** in the root `.env`. Never put them in an app/web file or in `NEXT_PUBLIC_` variables. Ensure the backend `CORS_ORIGINS` includes the exact frontend origin (the default is `http://localhost:3000`). Use the same Supabase project for frontend Auth and backend JWT verification.

Start the API as above, run the ingestion worker in another terminal, then start the frontend:

```powershell
cd apps/web
Copy-Item .env.example .env.local
# Replace the three public placeholders in .env.local.
npm ci
npm run dev
```

Open `http://localhost:3000`. Sign up or sign in with a confirmed Supabase Auth email account. On first use, enter a display name, IANA time zone, and player profile name. Upload a supported PDF, wait for the worker, inspect the source athlete rows and automatically captured page-2 Maximum Velocity/Player Load labels, review uncertain labels against the uploader-only private PDF, then explicitly link a ready row to the owned player. Manual proposal and confirmation remain available for missing, uncertain, or corrected labels. The dashboard, sessions, and analytics pages load accepted history. The frontend does not call Supabase Data API or compute analytical statistics; FastAPI is the authorization and calculation boundary. The frontend type contracts in `apps/web/lib/api/types.ts` are maintained against FastAPI's `/openapi.json`.

### AI Analyst setup

The Analyst uses the OpenAI Responses API from FastAPI only. Set `OPENAI_API_KEY` in the ignored root `.env` on the backend host; never put it in `apps/web/.env.local` or a `NEXT_PUBLIC_` variable. `OPENAI_MODEL` defaults to `gpt-6-luna`. The `.env.example` AI settings bound provider timeout, tool calls, question/context/result sizes, response length, date range, and daily runs per actor. `AI_MONTHLY_BUDGET_USD=5.00` and `AI_BUDGET_RESERVE_USD=0.10` enforce one **global** application estimate shared across every PlayerIQ user, using UTC calendar months. New provider calls stop at the usable threshold of $4.90, accounting for in-flight reservations. The 20-new-runs-per-actor/day limit remains separate. Apply Alembic through `0008_ai_budget_precision` with the privileged **PlayerIQ Dev** migration connection before testing AI routes with a restricted API login. No key is required for the fake-provider test suite. Without a configured key, chat creation is available but generation returns `ai_not_configured` (503).

The budget is an application-side estimate using reviewed model pricing; OpenAI billing is authoritative, and prepaid credits or Platform limits are separate. Review the pricing map when models or provider prices change. Unknown model pricing blocks AI calls. The monthly usage summary is internal only; no billing dashboard or public budget endpoint is provided. See [AI_ANALYST.md](docs/AI_ANALYST.md) for provider-request persistence, concurrency, and conservative handling of uncertain calls.

Visit `/app/analyst` to ask about accepted player history. Each answer displays verified facts, source-session links, an `analytics_v1` explanation, and a stale marker if accepted history changes. The session detail page can generate a scoped explanation. AI interpretation is separate from backend-calculated values. [AI_ANALYST.md](docs/AI_ANALYST.md) documents the fact registry, validation, privacy and retry policy.

If email confirmation is enabled in Supabase Dev, confirm the signup email before signing in. The project must have a configured Auth redirect URL for `http://localhost:3000/app`. The standalone ingestion worker must be running for an upload to advance beyond queued/processing. No production Supabase project is needed for local development.

## Ingestion worker

The API queues a durable job after a private upload. Its restricted role can insert only an owner-authorized job and does not read job rows; enqueueing uses a no-return insert to avoid requesting columns it cannot select. The separate worker claims and updates jobs. A server-side enqueue failure returns a safe upload error and attempts to remove the newly stored private object. Run the deterministic worker command from another terminal or schedule it on the backend host:

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
| `GET /v1/report-uploads?limit=&cursor=` | Uploader-only, cursor-paginated upload history with processing status and extracted row count when ready. |
| `GET /v1/report-uploads/{upload_id}` | Uploader-only status, findings, and candidate athlete rows. |
| `GET /v1/report-uploads/{upload_id}/chart-reviews` | Uploader-only chart proposal/review history. |
| `POST /v1/report-uploads/{upload_id}/chart-reviews` | Propose an exact printed page-2 `Player Load` or `Maximum Velocity` label for a selected source row UUID. |
| `POST /v1/report-uploads/{upload_id}/chart-reviews/{review_id}/confirm` | Confirm the proposed label and athlete match; keep anomalous speed held. |
| `POST /v1/report-uploads/{upload_id}/links` | Explicitly link one eligible row to the uploader's own player profile. |
| `GET /v1/report-uploads/{upload_id}/file` | Uploader-only private report download. |
| `GET /v1/players/{player_id}/sessions` | Authorized, paginated accepted sessions. |
| `GET /v1/players/{player_id}/sessions/{session_id}` | Authorized session metrics and source provenance. |
| `GET /v1/players/{player_id}/analytics/overview` | Versioned latest comparisons, top-speed record, highest recorded total-distance workload, highest-distance training session, and changes. |
| `GET /v1/players/{player_id}/analytics/trend?metric=&from=&to=&type=` | Accepted-value points with session type, change, and eligible weekly slope. |
| `GET /v1/players/{player_id}/analytics/outliers?type=&limit=` | Median/MAD workload results with source session IDs. |
| `GET/POST /v1/players/{player_id}/sessions/{session_id}/analysis` | Read or generate a creator-private, fingerprinted explanation of an accepted linked session. |
| `GET/POST /v1/players/{player_id}/chats` | List or create creator-private AI conversations. |
| `GET/POST /v1/players/{player_id}/chats/{thread_id}/messages` | Paginated history or an idempotent grounded AI answer. |

Only the reviewed five-page Activity Report layout is supported. Candidate rows do not become sessions by name matching. The worker first checks page-2 PDF text and positions, then uses bounded local OCR on the chart image if needed; the chart is raster in the reviewed source, so vector parsing adds no evidence. It reads exact printed labels, never bar heights. OCR needs a unique same-report athlete label match, a valid numeric shape, high numeric confidence, and agreement across two scales for automatic acceptance. Uncertain labels stay in review; absent labels stay missing, distinct from printed zero. The source observation retains the raw label, page/chart bounding box, extraction method, confidence or deterministic state, parser version, and row reference. The exact human-confirmed label becomes authoritative when corrected. A confirmed post-link correction updates the accepted metric and changes the player-history fingerprint. Speed readings above the configured review value stay held. `Player Load` is a source index of unknown definition, so its history is stored but cross-session comparisons are `not_comparable` until a verified definition/configuration is available. Zero-recorded rows are held. The analytics domain is pure and shared by HTTP and the Phase 5 AI tools; every result carries `analytics_v1`. Previously processed uploads are not automatically reprocessed by this release. Coach invitations and coach writes are deferred; coach read grants already have a structural authorization path, but no invitation endpoint is present.

## Tests and privacy

```powershell
python -m pytest -q
python -m ruff check apps/api db/migrations
python -m ruff format --check apps/api db/migrations
python -m mypy apps/api/app
```

Unit/API tests use generated keys, fabricated users, an in-memory fake Storage service, SQLite integration, and a synthetic PDF. Optional read-only development Supabase checks are described in [AUTH.md](docs/AUTH.md) and are disabled by default. The optional private-report test uses `PLAYERIQ_LOCAL_REPORT` only when explicitly set and never commits report data. `sample-data/` remains ignored except for its README.

Frontend checks:

```powershell
cd apps/web
npm run lint
npm run typecheck
npm test
npm run build
```

### Authenticated development smoke test

Use only a confirmed **PlayerIQ Dev** account and a synthetic report. Start API, worker, and frontend. In the browser: sign in → complete onboarding → verify dashboard empty states → upload a synthetic PDF → watch queued/processing/ready state → select a ready synthetic athlete row → propose and explicitly confirm its page-2 labels → link to your owned player → open the created session → inspect the dashboard, trend, and outlier states. A second account must receive 404 for the uploader's report and private PDF. This run is not automated by the repository because it requires a confirmed development account; the local Phase 4 check verified `/readyz` and the public sign-in screen but did not use a private GPS report or create an unconfirmable Auth user.
