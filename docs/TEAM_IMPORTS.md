# Automatic GPS report team import

## Workflow and authorization

An active coach/admin chooses a team on Upload GPS Report and submits **Upload and import team athletes**. This explicitly authorizes importing every identifiable extracted athlete into that team and sharing eligible accepted sessions. Session type is selected once; the default is `unknown`, never inferred from the PDF. The private upload path retains explicit personal row confirmation.

For an existing private upload, its uploader selects the team and session type on report review, then chooses **Assign team and import all athletes**. An already assigned report has an import panel with explicit sharing confirmation. No second PDF upload is needed. Only the uploader who is currently a coach/admin can request, retry, inspect or resolve import rows. A different team assignment returns 409. Existing accepted links must already belong to the destination roster/membership; assignment preserves session IDs and observations.

The PDF, source candidate rows, chart proposals and import row results remain uploader-private. Other team managers receive the roster and accepted team session projections, never raw review evidence. A player member sees only their own player/participant detail. Personal analytics/AI still require account ownership or an existing individual coach read grant; a team manager grant alone grants no personal AI access.

## Data model

Migration `0011_team_roster_import` follows `0010_team_creation_rls` without altering applied migrations.

| Record | Purpose |
| --- | --- |
| `players.owner_user_id` | Nullable UUID. The existing unique owner constraint still permits one canonical owned player per account; multiple NULL owners are unclaimed athletes. No Auth account is fabricated. |
| `players.origin_team_id` | Team provenance for unclaimed profiles and RLS bootstrap. A CHECK requires an owner or origin team. Runtime ownership/origin changes are not granted. |
| `team_roster` | `(team_id,player_id)` athlete relation, separate from login permissions. Contains creator, timestamp, optional first source row, parser/normalized label and revocation. Approved existing memberships are seeded into it. |
| `team_report_imports` | One request per upload: immutable team, initiating uploader, explicit type, queued/complete/needs_review/failed state, attempt count, safe error code and timestamps. |
| `team_report_import_rows` | One outcome per source row: player/session references, association method, outcome/reason, creation flags and manager resolution audit. |
| `team_roster_resolutions` | Immutable manager-confirmed association from an unclaimed profile to an already approved account's canonical profile, with team, source row and timestamp. |

Unclaimed athletes have no user membership, fake email, login permission or coach ownership. The existing `player_sessions` and `session_metric_values` remain canonical. Team roster membership is independent of participation. Registered approved profiles can be roster athletes too.

## Matching and metric rules

1. Preserve an existing source-row/session association. Conflicting confirmed evidence is held for review.
2. Reuse a unique active confirmed identity in exactly the report's destination-team scope, parser and normalized source label. Require a currently eligible roster athlete. Confirmation by an authorized manager establishes a source-to-athlete mapping; it never establishes new account ownership.
3. A unique unmatched label creates an unclaimed profile and provenance-bearing roster entry. Its first eligible row can create a session under report-level import authorization. This import association is **not** a human-confirmed identity mapping.
4. A later exact match to an unconfirmed import association may propose the same roster athlete, but does not merge another session into that history until the manager deliberately confirms it. No fuzzy matching or account display-name matching is performed. Source definition/configuration keys remain unchanged.
5. Duplicate/ambiguous/conflicting labels produce `identity_review`. No new session is accepted for unresolved rows. A manager can explicitly resolve each duplicate row to a different roster athlete or create separate unclaimed profiles. Duplicate labels do not produce reusable source mappings.

Identifiable `zero_recorded` and row-level `needs_review` athletes join the roster but receive no accepted workout. Zero is distinct from missing and does not prove nonattendance. Ready rows use the existing deterministic report validator and linking service, including same-player/date conflicts. Chart metrics may be missing or held while other table metrics are accepted. Existing automatic extraction, exact printed labels, manual corrections and held readings take precedence as before. No bar-height estimate, LLM or new OCR pipeline is involved. Player Load units/formula and provider thresholds remain unknown; comparability checks are unchanged.

## Deliberate account association

The uploader-manager can verify an imported source row and select an already approved account's roster profile. Only an unclaimed profile originating in this same team can be associated with a registered profile. Registered histories cannot be merged with each other. The service checks team scope and all dates first, creates immutable resolution evidence, moves canonical sessions and scoped identities while preserving their IDs and metric source references, updates import references, and archives the old unclaimed profile/roster entry in one transaction. A date conflict aborts the entire association. It never changes `owner_user_id` or grants membership. At most 1,000 source sessions can be resolved in one association.

**Confirm — This is me** remains explicit. On an imported row it performs the same audited association to the uploader's owned profile before confirming the source identity. Another player cannot open a coach's private report to claim a row; they join the team and the uploader-manager verifies their association. The existing chart/row quality restrictions still apply to personal session confirmation.

## API contracts

All routes require the existing verified Bearer token and uploader plus active team-manager authorization. Bodies reject unknown fields. Inaccessible resources return 404, association/team/type/date conflicts 409, and invalid eligibility/bounds 422.

| Route | Body / result |
| --- | --- |
| `POST /v1/report-uploads` | Existing multipart PDF plus optional `team_id`, `import_athletes=true`, `session_type=training|match|unknown`. Returns existing 202 upload contract. No import occurs unless explicitly requested; the web team upload requests it. |
| `POST /v1/report-uploads/{id}/team-import` | `{team_id, confirm_share:true, session_type}`. Assigns/queues or retries a failed run. Returns 202 `TeamImportOut`. Same upload/team/type repeat is idempotent; a different type cannot silently reinterpret accepted history. |
| `GET /v1/report-uploads/{id}/team-import` | Private request status, safe error, timestamps, backend counts, source row names/ordinals, canonical IDs, association/outcome/reason and resolution time. No request returns `import_not_found` (404). |
| `POST /v1/report-uploads/{id}/team-import/rows/{row_id}/resolve` | `{player_id:null|uuid, confirmed_source_label, confirm_association:true}`. Exact label is required. An existing associated row defaults to its current profile; a fully unresolved row with null target creates a separate unclaimed profile. Returns updated import results. |
| `GET /v1/teams/{id}/players` | Existing directory, now roster-backed. Adds `account_state=registered|unclaimed` and `participation_state=accepted_history|no_accepted_activity`. Only authorized entries are returned. |

Import rows use outcomes `accepted_session`, `existing_session`, `no_activity`, `identity_review`, `metric_review`, or `session_conflict`. Counts include each outcome, `total`, `created_players`, `created_sessions` and total `accepted_sessions` (including reused sessions). Association methods distinguish import provenance, confirmed identities, existing links, unconfirmed roster candidates, unresolved rows and deliberate manager confirmation.

## Worker, locking and recovery

The existing `python -m app.cli.process_ingestion --limit 10` command runs from the repository root with `PYTHONPATH=apps/api`, the existing restricted worker connection, and the existing restricted API connection. No public worker trigger is added. A bounded pass handles ingestion first, ready team imports next, and legacy chart backfill after that. Each ingestion/import/backfill consumes one limit unit; a new team report usually needs at least two units. Rerun the command or use the existing worker scheduling setup until the queue is drained. Restart a running worker to load this implementation.

The worker receives only SELECT on import request metadata. It still cannot read/write accepted player history. Import orchestration opens a restricted API transaction as the recorded uploader and repeats current authorization. Run identity/type/initiator fields are not updatable by runtime roles. Reports with rejected/deleted source state fail safely; an extracting/queued report waits for ingestion. Import attempts are capped at three; a failed run requires explicit authorized retry. No worker invokes OpenAI.

One report is processed atomically with a maximum of 200 extracted rows. Per-row deterministic conflicts are recorded using savepoints; unexpected errors roll back roster, sessions and outcomes, then persist only a safe failed-attempt code in a separate transaction. The UI shows queued until commit, followed by complete/needs-review/failed; it does not claim partial progress. Per-report and per-team advisory transaction locks serialize requests, assignments, roster matching and retries. Existing player/source locks serialize canonical linking and chart review. Unique constraints provide a second duplicate boundary. Retrying completed requests preserves IDs and outcomes. Deliberate repeated successful resolution is idempotent.

The directory supports up to 1,000 active roster athletes, and existing team analytics retain their 1,000-session history bound. Unsupported limits fail visibly. Accepted session/metric changes alter the existing `analytics_v1` history fingerprint; saved AI analyses become stale without another calculation engine.

RLS is enabled and forced on all new tables. Narrow column grants protect runtime updates; no PUBLIC/browser grants are introduced. `playeriq.is_roster_player(uuid,uuid)` is a private, non-inlineable SECURITY INVOKER lookup with fixed `search_path=pg_catalog`, following the existing creator helper pattern to avoid INSERT-policy recursion. A private invoker trigger rejects canonical `player_id` changes without matching audited OLD-to-NEW association evidence. Existing team creation helper/permissions remain intact. Downgrade refuses while unclaimed profiles exist rather than deleting or assigning their data to fabricated accounts.

## Verification and remaining manual checks

Verification on 2026-10-02: 97 backend tests passed (four opt-in checks skipped), 84 frontend tests passed, and Ruff, Python formatting, mypy, ESLint, TypeScript, Prettier and the production frontend build passed. Real restricted-role PlayerIQ Dev probes passed for team creation and the 18-athlete import, including audited account association, concurrent locking and cross-user denial. All probe writes rolled back; the explicitly synthetic source fixture was removed. Migration upgrade succeeded and generated downgrade SQL passed in a rolled-back transaction; the development head remains `0011_team_roster_import`. New tables have enabled/forced RLS, private helpers remain invokers, and ownership UPDATE/browser roster/worker history access are denied.

Isolated browser checks used synthetic Auth and API responses only: report import summary, deliberate association confirmation and roster-only activity were reviewed at 1440×900 and 390×844. Neither layout overflowed the page; tables scroll within their containers. Python and npm dependency audits found no known vulnerabilities. The ignored local virtual environment's pip tooling was updated; application dependencies were unchanged. The local backend package itself is not a PyPI dependency and is covered by repository tests rather than the dependency audit. No OpenAI call or private report inspection was performed. Live authenticated browser verification is still pending below.

Synthetic backend tests cover 18 athletes, roster-only zero/held rows, scoped confirmation/reuse, duplicate/conflicting identities, account association with preserved canonical IDs/fingerprint, same-date conflicts, private existing uploads, manual chart corrections/held readings, retry rollback, revoked authorization and cross-team/privacy isolation. Frontend tests cover sharing confirmation, progress, backend counts, roster state, association confirmation and errors. The opt-in real-role PostgreSQL import regression uses an externally prepared, explicitly synthetic fixture; all team/import/session writes roll back and fixture setup must be cleaned with its exact generated upload UUID. It also tests concurrent advisory lock exclusion, forbidden unaudited reassignment, denied worker history access, and browser/ownership grant restrictions.

Authenticated live browser verification remains manual when safe development Auth credentials are unavailable:

1. Sign in as a confirmed PlayerIQ Dev coach/admin. Upload a **synthetic** report to a selected team with explicit type; run the worker for at least two units and refresh the import panel.
2. Check all athletes in Players, including roster-only zero rows, and accepted sessions in Team Sessions/authorized drill-down. Review ambiguous rows and verify no guesses were accepted.
3. Assign/import an existing processed synthetic report with an accepted personal link. Confirm its session ID is preserved and retry does not duplicate athletes/sessions.
4. Approve a second development player's membership, deliberately associate their unclaimed row with their approved profile, and check their personal sessions/analytics match the canonical team data after reload.
5. In the second account, verify that the first uploader's review, import results, chart reviews and PDF return 404; unrelated team drill-down must also return 404. Check desktop and mobile layouts and keyboard controls.
6. Upload a later synthetic report: a confirmed scoped mapping may import automatically; an unconfirmed same-name candidate must remain in review. Confirm that suspicious chart readings remain unavailable. AI entry/privacy and the global budget are unchanged; no paid AI request is needed for these checks.
