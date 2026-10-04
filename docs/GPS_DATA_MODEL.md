# PlayerIQ GPS data model (public version)

This document describes the report structure supported by the Phase 1 adapter. It contains no original report pages, athlete identities, club identity, source activity identifier, or individual training values. The committed tests generate an independent synthetic five-page PDF. A private source report was reviewed locally to establish the labels and layout; that file is not part of this repository.

## Source format and scope

The supported input is a five-page, multi-athlete `ACTIVITY REPORT` PDF. Its first page carries an activity title, local header clock, total activity time, team label, and venue label. The fourth page has an athlete breakdown table. The fifth page has an `Averages` row at report scope. Other pages contain graphical summaries, including a period breakdown and athlete charts. The athlete table is selectable text; the graphical values are embedded images in the reviewed format.

The PDF does not provide a stable athlete ID, athlete exposure duration, timezone, confirmed activity start time, or confirmed session type. An activity report can list several athletes, including rows with zero distance. A zero row does not prove absence or participation. A source display name alone must never establish account ownership or merge existing histories. Authorized report-level team import may create separate unclaimed canonical athletes with explicit source provenance; later history reuse requires confirmed scoped evidence.

## Roster import and canonical history

Migration `0011_team_roster_import` separates roster athletes from registered account permissions. It adds nullable canonical player ownership with an origin team, a roster relation, import requests/outcomes, and immutable deliberate-association evidence. No GPS metrics or thresholds are invented. All extracted rows are considered (maximum 200 per import), including identifiable zero/held athletes who stay roster-only. Accepted sessions/metric observations use existing data types and normalization. Ambiguous labels remain unresolved, and unconfirmed later name matches do not merge history. Account association preserves session/observation IDs and uses the same analytics fingerprint. Exact schemas, grants, bounds and rules: [TEAM_IMPORTS.md](TEAM_IMPORTS.md).

## Metadata model

| Source item | Internal field | Rule |
|---|---|---|
| Activity identifier/title | `source_activity_id`, `source_title` | Preserve as source text; do not parse the identifier as a timestamp. |
| Header clock | `reported_local_datetime` | Keep naive/local until the timezone and clock meaning are confirmed. |
| `TOTAL TIME` | `activity_total_time_s` | Parse `H:MM:SS` at report scope only. Never assign it as athlete duration. |
| `TEAM`, `VENUE` | `source_team_name`, `source_venue_name` | Preserve as printed source labels. A PlayerIQ team is a separately created authorization workspace; the printed label alone does not assign a report to one. |
| Athlete name/position | `source_name`, `source_position_code` | Preserve by row ordinal; explicit owner-authorized linking happens later. |
| Period graphic | `report_periods` | Retain as unavailable until exact text extraction is supported. |

## Complete athlete metric inventory

“Direct” means printed by the GPS report, not necessarily directly measured by the device. The table values are extractable as PDF text. Chart labels are captured automatically where evidence passes the adapter's quality checks; otherwise they remain review-required or missing until uploader review.

| Exact source label | PlayerIQ key | Unit/type | Meaning and V1 treatment |
|---|---|---|---|
| `Distance (m)` | `total_distance_m` | m, `numeric(12,3)` | Total reported distance; primary running-volume metric. |
| `Meterage Per Minute` | `reported_meterage_per_minute` | m/min, `numeric(12,3)` | Source distance rate; athlete denominator unknown, so do not recompute from activity time. |
| `Overall (%)` | `source_overall_raw` | printed `%`, raw text and optional numeric | Definition unresolved; preserve exactly and exclude from analytics. Values may exceed 100. |
| `High Speed Distance (m)` | `reported_high_speed_distance_m` | m, `numeric(12,3)` | Source-classified high-speed running; threshold unknown. |
| `Accel&Decel Efforts` | `reported_accel_decel_efforts_combined` | count, integer | Combined acceleration/deceleration count; do not split into two metrics. |
| `Accel&Decel Efforts Per Minute` | `reported_accel_decel_efforts_per_min` | count/min, `numeric(12,3)` | Source effort rate; denominator unknown. |
| `Velocity Band 2 Distance (m)` | `velocity_band_2_distance_m` | m, `numeric(12,3)` | Source band 2 distance; zone boundaries unknown. |
| `Velocity Band 4 Distance (m)` | `velocity_band_4_distance_m` | m, `numeric(12,3)` | Source band 4 distance; not automatically sprint distance. |
| `Sprint Efforts` | `reported_sprint_efforts` | count, integer | Source sprint event count; threshold and bout rule unknown. |
| `Player Load` | `player_load_reported` | unspecified source units, `numeric(12,3)` | Priority V1 workload metric. Printed chart label captured automatically where reliable; uncertain labels require review. |
| `Maximum Velocity` | `maximum_velocity_kmh` | km/h, `numeric(12,3)` | Priority V1 top-speed metric. Printed chart label captured automatically where reliable; suspicious speeds stay held. |

The `Averages` row contains the nine table metrics in the same order. It is a **report aggregate**, never an athlete observation. The charts duplicate some table metrics; the table is the preferred text source. No universal high-speed, sprint, acceleration, or velocity-band threshold is specified in this format. The GPS provider and Player Load formula are unknown.

### V1 priority: top speed and Player Load

Both chart-only metrics appear on the session view and dashboard once an exact athlete-level value is captured and validated. The supplied workflow has **PDF only**. Page 2 prints a numeric label over each athlete's Player Load and Maximum Velocity bars, alongside an abbreviated athlete label; values are never inferred from bar height. The adapter tries PDF text and positional associations first. In the reviewed format the numeric and athlete labels are raster, so it uses bounded local OCR on the chart image. It requires exact, unique same-report athlete-label matching, regular chart placement, high numeric confidence, and two agreeing numeric reads for automatic acceptance. It preserves the printed raw string, parsed decimal, page/chart and compact box locator, extraction method, confidence or deterministic state, parser version, quality state, and source-athlete-row association. OCR uncertainty remains review-required or missing. Phase 3 manual transcription remains available: the uploader selects a source athlete row UUID, enters the printed numeric label, and explicitly confirms label and athlete match. The separate review record retains proposer, reviewer, review time, status, and resulting source-observation ID. Manual confirmation becomes authoritative, while automatic evidence remains in the audit trail. A missing label stays null, distinct from printed zero.

`Maximum Velocity` supports top-speed history and personal bests after quality review. A confirmed label above the configured 45 km/h review value is retained as `held` evidence and excluded from accepted metrics, even if entered by the uploader; resolution requires new, independently supported evidence. `Player Load` supports a source-specific workload observation; its units and formula are unknown. Its current `unverified:*` key cannot establish cross-session comparability by matching itself. A Player Load increase is a workload change, not automatically an improvement.

## Normalization and validation

Each extracted observation retains its exact source label, raw value and unit, parsed decimal when possible, page/row locator, scope, parser version, and quality state. Normalized candidates refer back to source observations. Numeric values must be finite and nonnegative; effort counts must be whole. High-speed and velocity-band distances cannot exceed total distance for the same row. Printed zero is distinct from an unavailable value. A zero-distance row is held for review rather than promoted to an accepted player session.

A configurable review rule flags a maximum velocity above 45 km/h while preserving the raw value. A peer-distance heuristic also flags unusually high distance when enough active rows exist. Neither rule clips, corrects, or diagnoses a value. `Overall (%)` remains unresolved even when it parses as a number. Definition-aware comparisons must keep source-specific metrics separate until provider definitions are known.

## Deterministic calculations and future fields

After explicit row-to-player linking, pure versioned backend functions calculate historical changes, comparisons, personal records, and workload anomalies from accepted stored metrics. The HTTP layer and Phase 5 AI Analyst share the same analytics service. Each result includes `analytics_v1` and source session/observation IDs; a history fingerprint detects stale saved analyses. The LLM may explain those results but cannot invent numerical facts. Future adapters could add vendor zone definitions, athlete duration, and more providers only when reliable source evidence is available. No such values are inferred by the current adapter.

Phase 5.5 adds an account-owned player identity, an explicitly confirmed source-label mapping, and optional team membership outside this GPS metric model. It does not introduce a provider athlete ID or infer one. Recognition uses a narrow parser/team/uploader scope and exact approved normalization, and still requires confirmation before a new accepted session exists. Team views read the same accepted `player_sessions` and `session_metric_values`; no source metric is duplicated for a team. See [PLAYER_IDENTITY.md](PLAYER_IDENTITY.md).

## Current adapter limits

Anonymous `You versus teammates` comparisons reuse the existing four accepted priority metrics and canonical sessions; no metric is added or inferred. The subject is excluded from the peer mean, and at least five accepted compatible other players are required per metric in the same report/type. Each count differs when metrics are unavailable. Printed accepted zero remains valid; missing/held observations do not become zero. Player Load comparisons remain same-report descriptive workload. Source evidence is retained internally but no peer evidence IDs are exposed by this projection. See [TEAM_COMPARISONS.md](TEAM_COMPARISONS.md).

The current adapter recognizes the reviewed five-page layout and extracts its header, table rows, report averages, and two page-2 printed chart metrics. The chart image layout is specific to this adapter. It does not estimate chart bars, parse other graphical metrics, or use an external OCR service. Period graphics remain unavailable. The worker automatically backfills these two chart metrics for supported completed `1.0.0` uploads, preserving original evidence, identity links, existing values and manual reviews. New evidence carries its current parser version and `backfill:chart_auto_v1` locator; only accepted readings fill missing accepted metric slots. Original missing observations remain in the audit trail, while candidate reading and subsequent linking use the appended replacement. This does not reprocess other metrics or create player sessions. Synthetic fixtures test text and raster charts, athlete matching, zero versus missing, suspicious speed, legacy backfill, manual authority, retry idempotency, report-versus-athlete scope, and explicit no-link behavior without publishing private GPS data.

## Team dashboard descriptive means

The backend recomputes same-report average distance and Player Load from accepted linked athlete metrics, rather than copying report-average source observations. Each mean has its own contributing-player count and `analytics_v1` provenance. Zero-recorded/held sessions, held metrics and missing metrics are excluded; accepted printed zero within an eligible session is included. Player Load remains a reported index; matching units and definition keys within one report permit a descriptive mean, including matching unverified keys only in this scope. This does not verify provider configuration or permit cross-report comparisons. Coach/admin responses include supporting accepted session/observation IDs; ordinary player summaries omit these averages.
