# Phase 1 report ingestion

## Flow and boundaries

```text
private PDF bytes
  → ActivityReportPdfV1Adapter.detect
  → ActivityReportPdfV1Adapter.extract
  → RawReport / RawAthleteRow / RawMetricObservation
  → ReportValidator.validate
  → row and metric quality states + findings
  → persist_inspection in caller-owned transaction
  → activity_reports / source_athlete_rows / source_metric_observations / ingestion_findings
  → future explicit row-to-player linking
  → future session_metric_values and accepted analytics
```

`IngestionService.inspect_pdf` is a side-effect-free entry point with a 25 MiB input limit. It selects the one supported five-page Activity Report adapter. The adapter relies on selectable PDF text and the page-4 table structure. It extracts page-1 activity metadata, 12 page-4 athlete rows with nine table metrics each, and nine page-5 report averages. It preserves raw labels, strings, units, parsed numbers, page/row locators, parser version, and source scope.

Page-2 `Player Load` and `Maximum Velocity` values and the period/summary graphics are embedded images in the reviewed PDF. The first adapter records those athlete metrics as **missing**, emits findings, and does not estimate bar heights or assign report totals to individual athletes. It leaves periods empty because the period graphic cannot be transcribed exactly from selectable text. It does not infer athlete duration, session type, timezone, participation, velocity thresholds, or player identity.

## Evidence, normalization, and quality

Source observations are what the report states, including anomalous `Overall (%)` values, zero-distance rows, and missing chart values. Validation is a separate pass. It maps known athlete labels through `metrics_v1`, checks numeric integrity and units, and returns normalized candidate values with comparability keys. `Overall (%)` remains raw source evidence and is excluded from normalized analytics because its definition is unresolved. Source-specific metrics have unverified comparability keys until provider definitions are known.

Quality is recorded at report finding, athlete-row, and metric levels. `ready` means a row has no blocking finding; `accepted` describes a usable metric candidate; `zero_recorded` means the source lists zero distance without establishing participation; `needs_review` flags a suspicious value or row; `missing` distinguishes an unavailable chart value from numeric zero; `unmapped` is reserved for unknown source labels. An anomalous metric never silently changes its raw value. The configurable default maximum-velocity review limit is 45 km/h. A peer-distance check flags values above three times the median when at least five rows have positive distance; it is a review heuristic, not a correction or football threshold.

The persistence function stores raw observations and findings for an already-authorized `ReportUpload` inside the caller's transaction and sets the upload to `awaiting_link`. It does not create `PlayerSession` or `SessionMetricValue` rows. A future authenticated endpoint will decide upload ownership, storage, quota, job execution, and explicit row-to-player links. Later linking may promote only reviewed, eligible metrics into accepted personal analytics and must keep their source observation IDs.

## Failure and duplicate behavior

An unsupported/malformed PDF produces `supported=false` and an `unsupported_layout` finding. If the expected athlete table cannot be found, no report is returned for persistence. A partially unparsed athlete row receives its own finding without destroying other rows. Exact repeated bytes are identified by SHA-256 per uploader; deleted uploads are excluded. The database adds a partial unique index for active duplicate hashes and a unique source-row link constraint.

## Known limitations

The first adapter is tied to the reviewed layout and does not support arbitrary providers, scanned PDFs, OCR, or chart transcription. Some extracted display names contain the PDF's repeated line-wrap text; they are never used as identity keys. Report averages are stored at report scope. The database migration was compiled offline and the models were exercised on SQLite; a live Supabase/PostgreSQL migration and RLS grant/policy checks require a configured project in the next phase.
