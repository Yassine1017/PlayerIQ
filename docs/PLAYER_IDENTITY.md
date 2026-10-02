# Player identity and team workspace (Phase 5.5)

## Identity boundary

Supabase Auth identifies the signed-in account. `profiles` stores its display preferences; `players` stores the account's owned PlayerIQ player record. A `source_athlete_row` is an observation from one uploaded PDF. Its printed athlete label is evidence, not an account identity. `player_source_identities` stores a separately confirmed relationship between a player and a source label. Historical `player_sessions` and `session_metric_values` remain the only canonical accepted performance history; personal and team pages query projections of those records.

Migration `0009_player_identity_teams` adds `teams`, `team_memberships`, `team_manager_grants`, `team_join_requests`, and `player_source_identities`. It adds an optional `team_id` to uploads and sessions, a backfilled `report_upload_id` to sessions, and `link_method`/`source_identity_id` provenance. No source identities are inferred or backfilled from old player names. Existing accepted manual links remain valid. An old processed upload can be assigned to a team by its uploader after the linked players are members of that team; neither the PDF nor source observations move or become team-visible.

## First confirmation

The uploader opens a processed report and selects a `ready` athlete row. The review UI shows the exact printed label, position, report date, distance, available chart value and quality state. A deliberate checkbox precedes confirmation. For the uploader's own player, `POST /v1/report-uploads/{id}/claim-as-self` requires the exact source label in the request, rechecks uploader ownership and player ownership, uses the existing link validator, creates the accepted session, and records the mapping in one transaction. If the row was already manually linked to the same player, confirmation preserves its original session type and creates only the mapping. Repeating the same claim is idempotent.

For an assigned team report, its uploader must also be a team coach or admin to confirm a member's row with `POST /v1/report-uploads/{id}/confirm-team-player`. The same exact-label, row-quality, duplicate, date, and accepted-metric checks apply. The resulting identity records the manager as confirmer and the row as provenance. A manager cannot confirm a row in someone else's upload or a player outside that team. An ordinary team player cannot open the uploader's report review or private PDF. Team managers may also use the existing manual link route; that route alone does **not** create a source identity.

`zero_recorded`, row-level `needs_review`, malformed or ambiguous dates, same-player/date conflicts, and a source label that appears more than once after normalization cannot establish an accepted session or identity mapping. A suspicious chart value remains held under the existing metric rules even if otherwise accepted row metrics are linked.

## Future recognition

The label normalizer applies Unicode NFKC, removes soft hyphens, repairs a hyphen only at a PDF line break, collapses whitespace, and case-folds. No fuzzy name similarity or account-display-name comparison is used. A mapping key contains the parser identity, that normalized label, and a narrow source scope:

- An explicitly team-assigned report uses its PlayerIQ team UUID.
- A private report with a printed team label uses the uploader UUID plus normalized printed team label.
- A private report with no printed team label is scoped to that individual upload, so it cannot recognize future reports.

The database permits only one active mapping per scope/parser/normalized label. Recognition returns a candidate only when the row is `ready`, its normalized label occurs exactly once in the report, one active mapping matches its parser and scope, the player is active, and any team membership is active. An inactive mapping, near match, other team, other uploader, other parser, departed player, or duplicated row label is unrecognized. The uploader review shows “Recognized · confirm”; it **never creates an accepted session automatically**. `POST /v1/report-uploads/{id}/links` accepts an optional `source_identity_id` and rechecks all recognition conditions, authorization, row membership, quality, and date conflicts before recording `link_method=recognized`. A manual link remains `manual`.

The owner can see connected identities in Profile and explicitly revoke one through `POST /v1/me/source-identities/{id}/revoke`. Revocation stops future recognition but retains historical accepted sessions, source provenance, and existing AI audit. A replacement mapping requires fresh explicit confirmation.

## Team boundary

A player with a profile may create a team, becoming its admin. Another account submits a join request using the team UUID; the creator/admin reviews the request and explicitly approves it as `player` or `coach`. Team membership is checked on every backend route, never inferred from a URL or browser role label. `team_manager_grants` is a restricted lookup for coach/admin RLS checks and avoids recursive membership policies. Team membership is separate from the older per-player `player_coaches` read grant.

| Role | Team visibility and actions |
|---|---|
| Player | Own personal dashboard, sessions, analytics, records, and AI. Team dashboard and session summaries include accepted participation counts and combined total distance. Team session detail and Players directory show only that member's own player data. |
| Coach | Team dashboard and accepted session detail for members, team Players directory and team-scoped deterministic player overview, sanitized team report summaries. May upload a report to the team and review/link its rows **only when they uploaded it**. |
| Admin | Coach permissions plus team creation ownership and approval of pending join requests. In Phase 5.5, the creator is the only approving admin. |

`GET /v1/teams/{id}/sessions` groups accepted player sessions by `report_upload_id`, not by date. It sums only accepted `total_distance_m` observations in the same report; it does not average Maximum Velocity or Player Load, rank players, or infer readiness. Team player drill-down calls the existing `AnalyticsService` with a team filter, so `analytics_v1` rules and source IDs still apply. Personal routes continue to require the owner or a pre-existing explicit per-player coach read grant. Team membership by itself does not unlock another player's personal chats or AI runs. The AI Analyst remains player-scoped and never receives team PDFs or teammate history through team membership.

The team Reports route returns upload ID, status, time and accepted player count for managers. It excludes filenames, PDF objects, unlinked candidate rows, chart review history, private source observations, and auth email. All raw report file and review routes still require the uploader. The private `playeriq` schema is not exposed through Supabase Data API; browser code receives no database role or server secret. Forced RLS and column-level grants protect the restricted API role; the worker role has no access to new team/identity tables.

## Limits and manual verification

The supported PDF has no stable provider athlete ID. Recognition therefore depends on the documented narrow label and scope evidence and always requires a human confirmation to create a session. Membership revocation, invitations, roster import, cross-player rankings, team AI, and team-level Player Load comparison are deferred. A previously processed report is not reprocessed for Phase 5.2 chart labels; its existing accepted row can still be claimed and assigned to a team. Assigning a previously private report does not silently turn its private-scope identity into a team-scope identity; a fresh explicit confirmation establishes the team-scope mapping. Duplicate-upload protection remains in force.

With a confirmed PlayerIQ Dev Auth account and a synthetic report: sign in, create/locate an owned player profile, upload/process the report, open review, select an eligible row, check its evidence, choose “This is me”, confirm, then verify My Dashboard and Profile. Create a team, have a second development account request membership by team ID, approve it, assign an eligible existing report or upload a new team report, confirm member rows, and verify the team dashboard, session grouping, player directory and role-specific detail. A second account must receive 404 for the first uploader's review and PDF. For a future synthetic report, a confirmed mapping should be shown as recognized but still require deliberate link confirmation. Use synthetic data only; never commit browser credentials or the private football PDF.
