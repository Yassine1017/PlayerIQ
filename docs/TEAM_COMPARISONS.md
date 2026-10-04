# You versus teammates

## Purpose and privacy

Team Dashboard and Team Session Detail now display a member's own accepted metric alongside an anonymous mean of **other** accepted athletes in that same team report and session type. The API binds the subject to the authenticated account; no subject, metric, type, position or cohort filter is accepted. Existing manager averages include the subject and remain a different descriptive result. Named teammate tables and drill-down remain manager-only; player participant detail remains self-only. PDFs, candidate rows, chart reviews, import outcomes and personal chats retain their existing privacy boundaries. No team AI tool or paid provider call is introduced.

At least **five eligible other players per metric** are required. Smaller cohorts return `insufficient_cohort` with the actual eligible count but no mean, differences, direction or peer evidence. This reduces disclosure risk; it does not guarantee anonymity, particularly when combined with information people already know. Do not add arbitrary cohort filters. The anonymous response omits teammate names, player/session/observation IDs, individual values, ranks, extrema and history hashes. Domain evidence IDs remain internal and are not logged or persisted by this feature.

## Calculation contract

The pure `analytics/team_comparison.py` domain functions consume strongly typed canonical session values supplied by `repositories/team_comparison.py`. The service handles authorization and decimal-string serialization; FastAPI handles HTTP. The domain imports neither FastAPI, authentication, SQLAlchemy nor HTTP schemas. Same-report source compatibility uses the same helper as existing manager averages. Personal longitudinal rules are unchanged.

Supported existing keys: `total_distance_m` (m), `reported_high_speed_distance_m` (m), `maximum_velocity_kmh` (km/h), and `player_load_reported` (source units, unspecified formula).

For a selected report, locate exactly one accepted subject session; compare only other accepted canonical sessions with that same type, including `unknown` only against `unknown`. Each metric requires accepted finite nonnegative values, the expected unit, matching definition ID and comparability key, and unique players and observation evidence. Held/missing/proposed/anomalous metrics, unaccepted sessions and roster-only rows do not contribute. Accepted printed zero does contribute. Duplicate/conflicting participants or source definitions fail closed as `not_comparable`; incompatible values are not silently discarded to manufacture a mean. The subject's missing/held metric returns `missing_metric`, rather than a peer-only result. No source report-average observation becomes a player value.

- Teammate mean: sum of eligible other players' values / their count.
- Signed absolute difference: subject value − teammate mean.
- Signed percentage difference: difference / teammate mean × 100, only when mean > 0.
- Direction: `above`, `below`, or `equal`, from unrounded Decimal values.

Every metric includes `analytics_v1`, `same_report`, its own teammate count, and minimum count 5. Raw values retain Decimal precision as strings. Display metres round half-up to whole metres, speed to one decimal, source index to three decimals (web formatting may display two), and percentages to four decimals. A zero baseline allows an absolute difference and no percentage; missing is never replaced by zero.

Player Load is a descriptive same-activity index. Matching `unverified:*` definitions are allowed only in this narrow report scope; they do not verify provider configuration or permit cross-report comparisons. Higher distance, high-speed distance or Player Load describes workload, not better performance. Higher speed than teammates does not establish improvement over time. No medical, readiness, injury or attendance inference is made.

## Endpoint and authorization

`GET /v1/teams/{team_id}/sessions/{report_id}/my-comparison`

Requires the existing verified Bearer token and active approved team membership. The service verifies an active account-owned canonical profile and its explicit membership association. A coach/admin with no membership player reference may use an account-owned active roster association. A conflicting membership reference, archived profile, team creator status alone, source label or display-name match cannot establish the subject. It never creates a mapping. Unclaimed athletes can contribute accepted peer observations without receiving Auth permissions.

The selected team report must have visible accepted canonical activity; inaccessible teams/reports return 404. At most 200 accepted sessions are loaded for the selected activity; exceeding the bound returns `team_comparison_limit` (422). No metric/profile reads across reports are needed. Existing restricted-role accepted-session/metric SELECT policies support the query; no migration, grants, RLS change or privileged function is added. No private source table or teammate profile lookup is performed to construct the benchmark.

Any query parameter returns `invalid_query` (422); it cannot switch subjects or narrow cohorts. Successful responses use `Cache-Control: private, no-store`. Top-level `status` is `ok`, `no_player_association` or `not_participating`; `ok` means an associated subject participated, not that every metric has a sufficient cohort. Individual metrics use `ok`, `missing_metric`, `insufficient_cohort` or `not_comparable`. Duplicate subject sessions yield unavailable metric comparisons.

Each metric returns key, unit, raw/display own value, raw/display teammate mean, raw/display signed absolute and percentage differences, direction, sample size, minimum count, scope and rule version. The only report ID identifies the selected authorized activity; no teammate evidence IDs are included.

## Freshness and UI

Results are recalculated on every authorized request and are not saved or cached. `comparison_fingerprint` defines an internal future-cache key covering the team/report/subject association, all projected session/player references, dates, types, quality, metric values, source IDs, definitions, supported metrics, rule version and minimum cohort size. A removed accepted session changes the projected cohort and hash. Current membership authorization must be checked before any future cache lookup. This fingerprint is not exposed to players and does not replace the personal AI fingerprint.

Dashboard shows the latest activity only, with an entry link to that exact session; no-participation never substitutes older history. Both views use the same endpoint and component, with neutral labels and metric-specific unavailable states. Refresh rereads accepted history, including confirmed chart corrections. Navigating to another report/team invalidates the component resource key; no cross-team data is retained. Existing manager means and participant tables are preserved.

## Verification and remaining manual checks

Synthetic domain/API tests independently specify the six-player example: own distance 3500 m, peers 2000/2500/3000/3500/4000 m, mean 3000 m, delta +500 m, display percent +16.6667%, peer count 5. They cover threshold boundaries, unit/definition conflicts, quality exclusion, zero/negative/equal differences, missing association/activity, wrong-team/type/report exclusion, duplicates, anonymous response keys, rejected subject/filter parameters, unauthorized/revoked access, confirmed peer chart correction and fingerprint changes. Existing full regression tests continue to cover parsing, chart capture/backfill, import, identity, AI grounding and global budget without paid calls.

Frontend tests exercise backend-supplied facts without recomputation, count/status rendering, Player Load wording, zero percentages, loading/error/retry, refresh corrections and team switching. Isolated Playwright checks use only synthetic Auth and API responses; they are not live authenticated integration tests.

Verified on 2026-10-04: the complete backend suite passed with 143 tests passed and 4 skipped; the complete frontend suite passed with 95 tests across 17 files. Ruff check/format, application mypy, Prettier, ESLint, TypeScript and the production frontend build passed. Isolated synthetic browser checks covered player and manager views, dashboard-to-session navigation, refresh, missing metrics, insufficient cohorts, no participation and no association at 1440 × 1000 desktop and 390 × 844 mobile. There were no console errors, framework error overlays or horizontal page overflow. Live authenticated browser/database verification remains pending below; no private reports or paid AI calls were used.

Manual live verification requires already available confirmed PlayerIQ Dev accounts; no credentials are requested or extracted:

1. Sign in as a development manager, upload/import a synthetic report with at least six eligible athletes and exact reviewed chart labels. Associate an accepted row to an approved player's canonical profile through the existing deliberate workflow.
2. Sign in as that player. Open Team Dashboard, follow the latest comparison link, and verify own values, other-player mean, signed differences, independent metric counts and self exclusion against the synthetic source.
3. Use a metric with four eligible other values: own value remains visible; mean and differences are suppressed. Use a missing own value, a held label and a zero peer baseline to check their distinct states.
4. Confirm a peer chart correction as its uploader. Refresh comparison as the player and verify the corrected mean. Confirm a suspicious speed stays held and does not enter the cohort.
5. Check an activity where the player has no accepted session; no older report is substituted. Verify coach/admin without an associated participating player gets an explicit unavailable state.
6. As the player, verify teammate drill-down/personal sessions/chats and uploader report/file/review/import routes still deny access. An unrelated or pending account must receive 404 for comparison. Verify browser responses contain no teammate IDs/names/evidence.
7. Repeat navigation, refresh and unavailable states on desktop/mobile and keyboard. No paid AI call is needed.

Restart FastAPI if it is running without reload to load the new endpoint. Migration head remains unchanged at `0011_team_roster_import`; no development database writes or migration are needed for this feature. Phase 6 remains future work.
