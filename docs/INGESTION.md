# Authenticated GPS report ingestion

## Phase 2 flow

```text
verified Supabase user
  → bounded multipart PDF validation (extension, MIME, magic, layout, SHA-256)
  → private Supabase Storage object + report_uploads + ingestion_jobs
  → worker claims due job with PostgreSQL SKIP LOCKED
  → ActivityReportPdfV1Adapter.detect / extract
  → RawReport / RawAthleteRow / RawMetricObservation
  → ReportValidator.validate
  → activity_reports / source_athlete_rows / source_metric_observations / ingestion_findings
  → uploader reviews candidate rows at GET /v1/report-uploads/{id}
  → uploader explicitly chooses eligible row and owned player at POST /v1/report-uploads/{id}/links
  → accepted player_sessions + validated session_metric_values with source observation IDs
```

The API reads at most `MAX_UPLOAD_BYTES + 1` bytes and rejects larger files (10 MiB default). A filename is display-only; storage keys contain the verified uploader UUID and a generated UUID. The API checks an uploader-scoped SHA-256 duplicate before storage and the database enforces a partial unique index. It stores the object privately, then creates the upload and job in one database transaction. If that transaction fails, it attempts to delete the uploaded object; an operator must reconcile any private orphan if cleanup also fails. No browser receives a permanent public object URL.

`python -m app.cli.process_ingestion --limit N` runs a bounded worker pass. The worker uses a separate restricted database login, claims due jobs with `FOR UPDATE SKIP LOCKED`, and can reclaim stale `extracting` locks. It verifies stored bytes against the upload SHA-256, then writes extraction, validation, and findings atomically. A report already persisted is not reinserted. Transient failures retry with bounded backoff and end in a safe rejection after three attempts. An unsupported layout is rejected with a finding; it never creates partial player sessions. A bad athlete row stays isolated from valid rows.

`IngestionService.inspect_pdf` remains a side-effect-free entry point with a 25 MiB intrinsic limit. The upload boundary is stricter by default. Its single adapter recognizes the reviewed five-page, selectable-text Activity Report layout. It extracts activity metadata, candidate athlete rows, table metrics, and report-level averages. The synthetic test document has 12 rows, but the parser does not assume the real roster size. It preserves source labels, raw strings, units, parsed values, page/row locators, parser version, and scope.

Page-2 `Player Load` and `Maximum Velocity` and period/summary graphics in the reviewed PDF are images. The adapter records unavailable exact athlete values as **missing** and emits findings; it does not estimate pixels, assign report totals to a player, or treat missing as zero. It does not infer athlete duration, session type, timezone, speed thresholds, participation, or identity. `Overall (%)` remains source evidence and is excluded from accepted analytics because its definition is unresolved. Source-specific values carry comparability keys that remain unverified until provider definitions are supplied.

Validation maps known athlete labels through `metrics_v1`, checks numeric integrity and units, and returns candidate normalized values. `ready` means no blocking row finding; `accepted` marks a usable metric; `zero_recorded` does not prove participation; `needs_review` holds suspicious values; `missing` records unavailable chart data. The configurable 45 km/h maximum-velocity review value and three-times-peer-median distance check are review heuristics, never corrections or provider thresholds. All anomalies retain original source values.

The uploader-only status response includes activity metadata, each candidate's source name/position, source observations, missing labels, quality state, findings, and existing links. The user must choose a row UUID and player UUID. The link transaction checks uploader ownership, player ownership, row membership, upload state, row eligibility, duplicate links, and same-player/date conflicts. It revalidates stored observations and copies only accepted athlete metrics with references to their source observations. Team averages, chart-only missing metrics, suspect metrics, and activity duration are never promoted as player values. `zero_recorded` and `needs_review` rows return a review-required error. Repeating the same accepted link is idempotent.

The raw PDF and unlinked teammate rows remain available only to the uploader. Ordinary player-session endpoints expose only accepted linked metrics, row-specific warnings, date/type/quality, and provenance IDs. A linked player does not gain access to the team PDF. Full authentication and role details are in [AUTH.md](AUTH.md).

## Known limits

Only the reviewed text-PDF adapter is implemented. Scanned PDFs, arbitrary GPS providers, CSV, OCR, exact chart transcription, manual quality resolution, deletion/retention workflows, and coach writing are later work. Source display names can contain PDF line-wrap artifacts and must never be used as identity keys. No live Supabase connection was available during implementation; run migrations and read-only live checks in a development project before deploying. All committed fixtures are synthetic.
