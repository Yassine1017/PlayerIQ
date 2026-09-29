# PlayerIQ GPS data model (public version)

This document describes the report structure supported by the Phase 1 adapter. It contains no original report pages, athlete identities, club identity, source activity identifier, or individual training values. The committed tests generate an independent synthetic five-page PDF. A private source report was reviewed locally to establish the labels and layout; that file is not part of this repository.

## Source format and scope

The supported input is a five-page, multi-athlete `ACTIVITY REPORT` PDF. Its first page carries an activity title, local header clock, total activity time, team label, and venue label. The fourth page has an athlete breakdown table. The fifth page has an `Averages` row at report scope. Other pages contain graphical summaries, including a period breakdown and athlete charts. The athlete table is selectable text; the graphical values are embedded images in the reviewed format.

The PDF does not provide a stable athlete ID, athlete exposure duration, timezone, confirmed activity start time, or confirmed session type. An activity report can list several athletes, including rows with zero distance. A zero row does not prove absence or participation. PlayerIQ must never link a row to a player profile from the display name alone.

## Metadata model

| Source item | Internal field | Rule |
|---|---|---|
| Activity identifier/title | `source_activity_id`, `source_title` | Preserve as source text; do not parse the identifier as a timestamp. |
| Header clock | `reported_local_datetime` | Keep naive/local until the timezone and clock meaning are confirmed. |
| `TOTAL TIME` | `activity_total_time_s` | Parse `H:MM:SS` at report scope only. Never assign it as athlete duration. |
| `TEAM`, `VENUE` | `source_team_name`, `source_venue_name` | Preserve as source labels; V1 has no team entity. |
| Athlete name/position | `source_name`, `source_position_code` | Preserve by row ordinal; explicit owner-authorized linking happens later. |
| Period graphic | `report_periods` | Retain as unavailable until exact text extraction is supported. |

## Complete athlete metric inventory

“Direct” means printed by the GPS report, not necessarily directly measured by the device. The table values are extractable in Phase 1. Chart-only values are registered but marked missing by the current adapter.

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
| `Player Load` | `player_load_reported` | unspecified source units, `numeric(12,3)` | Chart-only source load index; exact value unavailable to the Phase 1 text adapter. |
| `Maximum Velocity` | `maximum_velocity_kmh` | km/h, `numeric(12,3)` | Chart-only top speed; exact value unavailable to the Phase 1 text adapter. |

The `Averages` row contains the nine table metrics in the same order. It is a **report aggregate**, never an athlete observation. The charts duplicate some table metrics; the table is the preferred text source. No universal high-speed, sprint, acceleration, or velocity-band threshold is specified in this format. The GPS provider and Player Load formula are unknown.

## Normalization and validation

Each extracted observation retains its exact source label, raw value and unit, parsed decimal when possible, page/row locator, scope, parser version, and quality state. Normalized candidates refer back to source observations. Numeric values must be finite and nonnegative; effort counts must be whole. High-speed and velocity-band distances cannot exceed total distance for the same row. Printed zero is distinct from an unavailable value. A zero-distance row is held for review rather than promoted to an accepted player session.

A configurable review rule flags a maximum velocity above 45 km/h while preserving the raw value. A peer-distance heuristic also flags unusually high distance when enough active rows exist. Neither rule clips, corrects, or diagnoses a value. `Overall (%)` remains unresolved even when it parses as a number. Definition-aware comparisons must keep source-specific metrics separate until provider definitions are known.

## Deterministic calculations and future fields

After explicit row-to-player linking, backend functions may calculate historical changes, comparisons, personal records, and workload anomalies from accepted stored metrics. The LLM may explain those results but cannot invent numerical facts. Future adapters could add exact chart transcription, vendor zone definitions, athlete duration, and more providers only when reliable source evidence is available. No such values are inferred in Phase 1.

## Current adapter limits

The Phase 1 adapter recognizes the reviewed five-page layout and extracts its header, table rows, and report averages. It records `Player Load`, `Maximum Velocity`, and graphical period values as unavailable. It does not perform OCR or estimate chart bars. The synthetic fixture tests multiple athlete rows, zero versus missing, anomalous percentages and speed, report-versus-athlete scope, and explicit no-link behavior without publishing private GPS data.
