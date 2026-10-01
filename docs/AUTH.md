# Phase 2 authentication and database security

Phase 5 migration `0006_ai_analyst` keeps AI runs, tool-call audit, chat threads, and chat messages in the private `playeriq` schema. The restricted API login receives SELECT/INSERT on these tables and UPDATE only for AI run completion; browser `anon`/`authenticated` roles receive none. Runs and audits belong to their actor and require current player access. Threads and messages belong to their creator, so a player cannot read a coach's chat or vice versa. Revoking a coach grant removes access on the next request. See [AI_ANALYST.md](AI_ANALYST.md) for the provider/data boundary. `OPENAI_API_KEY` is a backend-only environment variable.

## Request trust path

Supabase Auth issues an access token. The browser sends it as a Bearer token to FastAPI. FastAPI reads the project JWKS at `SUPABASE_URL/auth/v1/.well-known/jwks.json` (cached for at most `JWKS_CACHE_SECONDS`) and verifies an asymmetric signature, `iss`, `aud`, `exp`, and UUID `sub`. HS256 tokens, missing key IDs, anonymous users, and invalid tokens are rejected. Only the verified UUID becomes the application actor. Editable user metadata, request bodies, and frontend roles cannot grant access. When keys are unavailable, authentication fails closed with 503.

For each request, the API opens a transaction using a restricted PostgreSQL login, checks that it belongs to `playeriq_api` and is neither superuser nor `BYPASSRLS`, and sets `playeriq.current_user_id` locally to the verified actor. Ownership services enforce resource access, and RLS policies provide a second boundary. The custom setting is transaction-local, so a pooled connection cannot carry one request's actor into another. The worker has its own restricted `playeriq_worker` login and never accepts a user-supplied actor.

For ingestion jobs, the API has only `INSERT` and an owner-scoped RLS insert policy. Its enqueue statement requests no returned job columns; an ORM insert with `RETURNING` would require `SELECT` and fail. The API cannot read, update, or delete job rows. The worker has `SELECT` and `UPDATE` for claiming and processing, with no API-role membership required. This is an application insert correction; the existing grants and policies remain in force.

## Resource access

| Resource | Current rule |
| --- | --- |
| Player profile and sessions | Owner read. An active pre-existing coach grant can read a player, but coach invitations and writes are deferred. |
| Upload, candidate athlete rows, raw PDF | Uploader only, even after an athlete row is linked. |
| Row linking | Uploader must also own the target player. A row must belong to that upload and have `ready` quality. |
| Session metrics | Only accepted, validated athlete observations are copied, retaining source observation IDs. Report/team aggregates are excluded. |
| Chart reviews | Uploader alone may list, propose, and confirm values for ready rows in their report. The selected row UUID, not display name, controls the athlete match. Linked players see only their own confirmed metric and provenance summary through the session route. |
| Analytics | Owner or active read-granted coach may query the selected player's accepted sessions. A player ID alone conveys no access. |

Inaccessible IDs return 404. A linked player's session view contains only their linked row's metrics and row-specific warnings; it does not include teammate rows or the full report. The private `playeriq` schema must **not** be added to Supabase's exposed API schemas. The report Storage bucket must be private; the API uses a server-only Storage secret and checks upload ownership before streaming a raw PDF. No permanent public URL is created.

## Development project configuration

1. Create a separate **development** Supabase project. Use its project URL for `SUPABASE_URL`. Configure Supabase Auth to issue asymmetric access tokens; the JWKS endpoint must publish the signing key. The audience is normally `authenticated`.
2. In Storage, create `playeriq-reports` as a **private** bucket. Set its file-size limit at or above the configured API limit and allow `application/pdf`. Do not add public `storage.objects` policies. The server-only secret key must be available only to API and worker processes.
3. Apply Alembic migrations with a separate privileged migration connection. Migration `0003_phase2_access` creates NOLOGIN group roles, revokes browser grants on `playeriq`, grants only needed table operations, adds RLS policies, and forces RLS on domain tables. Migration `0004_secure_alembic_version` revokes Data API grants on the public Alembic version table and enables RLS. Neither migration creates login credentials.
4. In the SQL editor or with a privileged development connection, create distinct login roles and give them group-role membership. Replace both placeholder passwords with unique generated secrets locally; never commit or paste them into chat:

```sql
CREATE ROLE playeriq_api_login LOGIN INHERIT PASSWORD '<unique-api-password>';
CREATE ROLE playeriq_worker_login LOGIN INHERIT PASSWORD '<unique-worker-password>';
GRANT playeriq_api TO playeriq_api_login;
GRANT playeriq_worker TO playeriq_worker_login;
```

If the platform's role policy disallows role creation from your chosen migration connection, have a project administrator run the migration and role SQL. Keep the privileged migration URL separate from runtime variables. Use the restricted API login for `DATABASE_URL` and the restricted worker login for `WORKER_DATABASE_URL` when running services. Neither may own PlayerIQ tables, be superuser, have `BYPASSRLS`, or hold the other group's membership. The application rejects superuser/BYPASSRLS and missing group membership at runtime; verify the remaining separation during project setup.

5. In `.env`, set `DATABASE_URL`, `WORKER_DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_STORAGE_SECRET_KEY`, and optionally `SUPABASE_JWT_AUDIENCE`, `SUPABASE_STORAGE_BUCKET`, `JWKS_CACHE_SECONDS`, `MAX_UPLOAD_BYTES`, `CORS_ORIGINS`, and validation review thresholds. `.env.example` is placeholders only. The Phase 4 frontend uses the same project's URL and enabled **public publishable key** in its ignored `apps/web/.env.local`; this backend does not need that key. Never expose either database password or the Storage secret to the frontend.

For a fresh development database, run `python -m alembic upgrade head` with the privileged migration URL temporarily in `DATABASE_URL`, then restore the restricted API URL. `python -m alembic current` should show `0008_ai_budget_precision`. Migration `0005` adds the uploader-only review table and policies; API updates/deletes of session metric values are restricted to the uploader's linked session and the two chart metric keys. The schema and RLS policies were applied to a separate development Supabase project through its migration API. Restricted runtime logins were verified previously; the final real-PDF browser retry remains manual.

## Verification

`GET /healthz` needs no credentials and checks only the process. `GET /readyz` needs no credentials and returns 200 only after a successful database probe and API-role check. A signed-in development user can then call `GET /v1/me` using a real Supabase access token; never paste that token into chat or commit it. Run `python -m pytest -q` for synthetic tests.

Optional live database checks are disabled by default. Set `PLAYERIQ_LIVE_TEST=development`, `PLAYERIQ_TEST_DATABASE_URL` to the **restricted development API** connection, and `PLAYERIQ_TEST_PROJECT_REF` to the exact development project reference, then run `python -m pytest -q apps/api/tests/test_live_supabase.py`. The test performs read-only role, migration, and RLS checks; it creates no users, rows, or reports. Do not run it against production.

Supabase reference: [JWT/JWKS](https://supabase.com/docs/guides/auth/jwts), [Postgres RLS](https://supabase.com/docs/guides/database/postgres/row-level-security), [Storage access control](https://supabase.com/docs/guides/storage/security/access-control), and [database connections](https://supabase.com/docs/guides/database/connecting-to-postgres).
