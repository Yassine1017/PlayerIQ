# PlayerIQ operational runbook

Reviewed 2026-10-05 against the current repository. This document defines recovery procedures and proposed launch policies. It does not configure hosting, backups, alerts, retention jobs or deletion endpoints. No restoration/deletion was performed. Development verification uses only PlayerIQ Dev and synthetic data; an incident operator must verify the intended project before acting.

## 1. Ownership and current controls

The project owner is the incident/release owner until another operator is assigned. Keep deployment IDs, project IDs, private backup locations and incident notes in an access-controlled operations record outside Git.

| Area           | Available now                                                                           | Required before production                                              |
| -------------- | --------------------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| API            | `/healthz`, `/readyz`, request IDs, controlled HTTP errors, API JSON logs               | External probes, alert recipient and incident owner                     |
| Worker         | Durable jobs, retry/error state, stale-claim recovery, bounded CLI passes               | Scheduled execution, scheduler heartbeat and aggregate queue monitoring |
| Authorization  | Restricted roles, RLS, uploader-only review, explicit identities                        | Live authenticated release checks and restore rehearsal                 |
| AI             | Request reservations/cost estimates, global budget, private audit, history fingerprints | Failure monitoring and accounting reconciliation after recovery         |
| Data lifecycle | Private Storage and internal object-removal adapter                                     | Authorized deletion workflow, retention schedule, backup expiration     |
| Releases       | Git history, tests and Alembic chain                                                    | Hosted artifact inventory, CI and rehearsed rollback                    |

Proposed launch targets: recovery point objective (RPO) **24 hours**, recovery time objective (RTO) **4 hours**. These are planning targets, not measured guarantees. Rehearse a synthetic restore before launch, quarterly thereafter and after material migration/hosting changes; record achieved times.

## 2. Backup restoration

### Inventory and snapshot

- **Database:** PlayerIQ data/schema, Alembic revision, Auth identity dependencies, custom roles, grants, policies and private functions. Confirm the backup method covers these; a PlayerIQ-table-only dump cannot recreate Auth or privileges.
- **Storage:** separately back up private report objects with keys, sizes, SHA-256 checksums and a paired database snapshot reference. Manifests are private. Database backups contain Storage metadata, **not PDF bytes**. See [Supabase database backups](https://supabase.com/docs/guides/platform/backups).
- **Release:** record frontend/API/worker commit/artifact IDs, schema revision, configuration variable names, parser/rule versions and UTC snapshot times. Keep actual secrets only in the host secret manager with controlled recovery access.
- **Off-site recovery:** encrypted copies with separate access controls. Verify the current project's plan and available restore window; automated backups/PITR are not assumed. For manual exports follow the current [Supabase backup/restore guide](https://supabase.com/docs/guides/platform/migrating-within-supabase/backup-restore) and CLI help. Never put credential-bearing connection strings on command lines or in Git.

Pause uploads/review/import writes and worker execution, allow transactions to finish, then capture the database and object manifest/bytes. If writes cannot be paused, record a consistency cutoff and reconcile referenced objects before claiming a complete snapshot. Backup success requires verified checksums and restore access.

### Restore procedure

1. Record cause, target project, approved recovery point, operator and expected loss window. Stop affected writes, workers and new AI generation at the hosting/ingress layer. There is no application maintenance switch yet. Preserve current state privately when appropriate for investigation.
2. Rehearse on an explicitly approved isolated environment using synthetic data. For an incident, select a valid pre-incident database snapshot and paired object backup. Provider restoration causes downtime; do not restore over an unrelated project.
3. Restore the database using the provider's supported procedure. Restore required Auth identities/configuration and check foreign keys. Never remap users by name/email or invent confirmed identities. A new-project restore requires destination Auth/JWKS configuration, not assumed reuse of the old endpoint.
4. Restore paired objects into a **private** bucket. Verify database-referenced keys and SHA-256 without printing reports. Missing/mismatched objects block ingestion/review recovery. Inventory extra objects separately; do not purge blindly.
5. Verify custom roles/functions, grants, enabled/forced RLS and browser denial. Provider backups may not preserve custom-role passwords: recover/reset them through the secret manager, then configure distinct restricted API and worker logins. Never give runtime roles superuser, table ownership or BYPASSRLS to bypass errors. See [AUTH.md](AUTH.md).
6. Compare restored Alembic revision with the release artifact. Select compatible code; review additive upgrades if necessary. A restore does not authorize automatic downgrade or `alembic stamp`. Confirm Auth, CORS, public frontend origin, private bucket and runtime configuration all identify the destination environment.
7. **Keep new AI generation disabled.** An older snapshot can omit provider usage/holds billed afterward. Reconcile private provider accounting and the incident record, preserving uncertain reservations conservatively. Never reset the $5 budget, erase accounting or replay pending requests. Leave generation unavailable if reconciliation cannot be completed.
8. Run readiness, restricted-role/RLS checks and synthetic authenticated manager/player/unrelated-account tests. Verify accepted history, uploader-only evidence, import/link idempotency, chart correction/fingerprint changes and anonymous comparison thresholds. Use fake AI responses or saved synthetic evidence without paid calls.
9. Reapply completed deletion records newer than the snapshot **before reopening access**. Restart one bounded worker pass and inspect persisted outcomes before resuming the schedule. Reopen writes/AI only after consistency, privacy and accounting checks pass. Record measured RPO/RTO and limitations.

No restore rehearsal or current hosted-backup configuration was verified by this documentation task.

## 3. Private-report retention and deletion

### Proposed launch policy — not yet enforced

The owner must approve these suggested periods alongside data residency/retention requirements before launch. They are not implemented privacy guarantees.

| Data                                        | Proposed retention                                                          | Dependency considerations                                                 |
| ------------------------------------------- | --------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| Raw private PDFs                            | 90 days from upload, or earlier authorized removal                          | Notify before expiry; removal prevents later evidence review/reprocessing |
| Unlinked source rows/observations           | 90 days from upload                                                         | Remove only when no session, identity, review or import depends on them   |
| Accepted sessions/necessary provenance      | While account/team history is active; support explicit deletion             | Resolve team-shared scope; never cascade away other athletes              |
| AI questions/answers/evidence/tool payloads | 90 days                                                                     | Reviewed pruning must preserve budget integrity                           |
| Minimal AI accounting                       | 13 months of request/status/pricing/tokens/cost, retaining unresolved holds | Separate personal payload retention from cost/reservation integrity       |
| Operational logs                            | 30 days, excluding credentials/report/chat contents                         | Host configuration pending; incident exceptions need owner/expiry         |
| Database/object backups                     | Target 30-day rotating window, subject to host capabilities                 | Encrypted and restricted; deletion becomes final as snapshots expire      |

PDFs are not automatically expired. There is **no implemented `DELETE /v1/report-uploads/{id}`**, account-erasure API or retention scheduler. The Storage adapter's `delete()` is a low-level cleanup operation, not an authorized user deletion workflow. Identity revocation stops recognition and preserves sessions; it does not delete data. See [INGESTION.md](INGESTION.md) and [PLAYER_IDENTITY.md](PLAYER_IDENTITY.md).

### Approved deletion procedure/design

1. Verify actor and scope: raw evidence only, session, whole report or account. Store approved identifiers privately. Ownership of one linked row does not authorize erasure of a team PDF or other athletes' data.
2. Inventory dependencies: upload/job/activity/periods, source rows/observations, chart reviews, identities, links, sessions/metrics, roster imports/resolutions, saved AI evidence and budget ledger. Foreign keys generally use `NO ACTION`; setting `deleted` neither erases data nor resolves dependencies.
3. Pause the exact scope and concurrent review/import/history writes. There is no complete deletion lock/tombstone protocol today. Before execution, provide a reviewed maintenance transaction/script with explicit scope, minimal privileges and recovery handling. Do not improvise broad SQL deletes or runtime grants.
4. Remove exact object keys via the Storage API and verify absence. Never delete `storage.objects` metadata directly; that leaves physical objects orphaned. See [Storage deletion](https://supabase.com/docs/guides/storage/management/delete-objects). Database/Storage changes are not atomic: keep a durable private deletion manifest and reconcile partial failures before declaring completion.
5. Apply reviewed database disposition in dependency order. Evidence-only removal preserves necessary canonical provenance and explicit evidence-unavailable state. Accepted-data removal must refresh history fingerprints and invalidate/remove dependent saved AI evidence. Preserve required budget accounting. Never reassign sessions just to satisfy foreign keys.
6. Verify uploader/player/team views, comparisons, AI references, object absence and privacy. Record operator/time/action/IDs without retaining deleted report text. Failed steps remain incomplete, with an explicit retry plan.
7. Restrict backup copies until scheduled expiration; do not promise immediate snapshot erasure. Keep a minimal deletion ledger outside the restore set and replay it before restored access, so recovery cannot resurrect deleted material silently.

This procedure is a runbook/design, not an executable deletion feature. Retention enforcement and authorized user deletion remain release prerequisites.

## 4. Job monitoring and recovery

### Existing worker

Run from the **repository root** with the existing ignored backend environment:

```powershell
Set-Location 'C:\Users\Computia.ME\Desktop\PlayerIQ-public'
& .\.venv\Scripts\python.exe -m app.cli.process_ingestion --limit 10
$workerExitCode = $LASTEXITCODE
if ($workerExitCode -ne 0) { throw 'PlayerIQ worker pass failed; inspect redacted logs.' }
```

This processes real queued work when executed; it was **not run** for this task. `--limit` accepts 1–100 and bounds ingestion/import/backfill work. The process exits after a pass, is not a daemon, and successful passes may be silent. Both restricted connections are needed for import/backfill; otherwise a successful pass can leave those queues untouched.

Ingestion uses `FOR UPDATE SKIP LOCKED`; `extracting` claims older than five minutes are eligible for recovery. Storage/processing failures normally retry after 30 and 60 seconds and reject on the third recorded failed attempt. Crash recovery is separate from that handler. Unsupported layouts/hash mismatches are rejected without normal transient retries. Team imports have up to three attempts then require explicit authorized retry. Backfill errors stop the pass; reruns preserve existing evidence/accepted slots. Review-required, held and zero-activity states are not infrastructure failures.

**Exit zero does not prove ingestion success:** handled job failures can be persisted while the CLI succeeds. Ingestion has priority over imports/backfills; backlog can delay those queues. Monitor persisted outcomes alongside process health.

### Proposed monitors — not configured

| Signal                          | Initial threshold                                              | Response                                                                          |
| ------------------------------- | -------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| `/healthz`, `/readyz`           | Every minute; alert after 3 failures                           | Separate process from DB/role outage; neither probes Storage/Auth/OpenAI/worker   |
| Scheduled worker heartbeat/exit | 2 missed scheduled passes or nonzero exit                      | Check scheduler/configuration and redacted logs                                   |
| Due ingestion backlog           | Oldest due time over 10 minutes                                | Check worker/Storage/retry availability                                           |
| Stale extracting claim          | Over 6 minutes and survives next scheduled pass                | Investigate recurring crashes; let existing recovery act                          |
| Terminal job/import failure     | Any new processing rejection or failed import                  | Distinguish unsupported report from infrastructure failure; inspect code/attempts |
| Ready team-import queue         | Oldest eligible import over 10 minutes                         | Check both connections, permissions and ingestion starvation                      |
| Legacy chart backfill           | Pass failure or repeated unresolved eligible uploads           | Inspect audit/quality; uncertain labels stay manual review                        |
| API/AI failures and budget      | Sustained failures or reservations near usable threshold       | Preserve holds; distinguish provider outage and expected budget exhaustion        |
| Backups                         | Last verified paired backup over 24 hours or integrity failure | Escalate; unverified snapshots are not healthy                                    |

Initial scheduler target: one minute, bounded runtime, no accidental overlapping passes. Record start/end/exit/outcome metadata externally and tune alert windows to measured processing times. No scheduler, heartbeat endpoint, metrics exporter or alert destination is added here.

Use these aggregate-only queries as a trusted operator in the intended project's SQL console or authorized monitoring connection. They expose no athlete names/report text/raw metrics. Do not grant global read access to the runtime API/browser roles for monitoring.

```sql
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '5s';
SELECT status, count(*) AS jobs, min(created_at) AS oldest_created_at
FROM playeriq.ingestion_jobs GROUP BY status ORDER BY status;

SELECT count(*) AS due_jobs, min(next_attempt_at) AS oldest_due_at
FROM playeriq.ingestion_jobs
WHERE status IN ('queued', 'failed_retryable') AND next_attempt_at <= now();

SELECT count(*) AS stale_claims, min(locked_at) AS oldest_lock_at
FROM playeriq.ingestion_jobs
WHERE status = 'extracting' AND locked_at < now() - interval '6 minutes';

SELECT status, last_error_code, count(*) AS jobs
FROM playeriq.ingestion_jobs
WHERE updated_at >= now() - interval '24 hours'
  AND status IN ('failed_retryable', 'rejected')
GROUP BY status, last_error_code ORDER BY status, last_error_code;

SELECT i.status, count(*) AS imports, min(i.created_at) AS oldest_created_at
FROM playeriq.team_report_imports AS i
JOIN playeriq.report_uploads AS u ON u.id = i.upload_id
WHERE i.status = 'failed'
   OR (i.status = 'queued' AND u.status IN ('awaiting_link', 'rejected', 'deleted'))
GROUP BY i.status ORDER BY i.status;
ROLLBACK;
```

These measure current state, not historical throughput. Store successive outcomes in the monitor. Actor-scoped API queries can filter rows and cannot prove system-wide health.

### Triage

Check scheduler execution, due-job state, readiness, then redacted warnings (`ingestion_retry`, `ingestion_worker_failed`, `team_import_failed`). The API configures JSON logs; the standalone CLI currently does not call that formatter and has no success/heartbeat output. Host capture must monitor its actual stderr/exit behavior. Successful backfill info messages may be hidden at default CLI logging levels.

Fix dependency/permission/configuration causes without exposing credentials or disabling RLS. Rerun a bounded pass in the intended environment and verify persisted outcomes. Respect next-attempt times, quality review and authorized import retry. Do not reset attempts/locks or accept held metrics just to clear an alert. No paid AI request is needed for ingestion recovery.

## 5. Release and rollback

Before release, record known-good frontend/API/worker artifacts and compatible Alembic revision. Current local head is `0011_team_roster_import`, not a live-project claim. Run frontend tests/lint/typecheck/build, backend tests/Ruff/mypy, migration and synthetic authorization checks. Verify a paired backup, separate migration/runtime credentials and Auth/CORS/bucket configuration. Record code deployments and schema changes separately.

### Application rollback

1. Identify regression and exact known-good artifact. Suspend affected writes/worker/AI while checking schema compatibility and in-flight operations.
2. Promote/redeploy the previous immutable artifact through the configured host, or build the reviewed commit in a separate clean checkout. Roll back frontend/API/worker together when contracts require it. Never reset the shared checkout, force-push `main` or rewrite history.
3. Preserve current secrets/configuration and database. Code rollback does not undo migrations, sessions, reviewed labels or provider charges. If old code cannot read the current additive schema/API contract, keep maintenance active and ship a forward correction.
4. Verify readiness and synthetic authentication/upload/worker/linking/comparison checks, privacy and budget integrity. Resume and monitor queue/errors; record outcome. Hosting-specific commands belong in the release record after hosts are configured; no deployment IDs are invented here.

### Database rollback

Prefer reviewed forward correction. Never run `alembic downgrade` automatically: it can remove tables, grants, policies or accepted/audit data. Rehearse a proposed downgrade on a synthetic clone and inspect dependency/grant impact under an approved recovery plan. A justified data-incident restore follows Section 2, including Storage consistency, deletion replay and AI accounting. It can lose valid later writes; application rollback normally does not.

Keep a private incident record with UTC times, operator, environment, error codes, release/schema before/after, manifest/recovery point, approved actions, checks, loss window and remaining work. Do not copy keys, JWTs, PDFs, athlete names or full chats into public issues/logs.

## 6. Pre-launch checklist

- Assign incident owner/alert recipient; configure and exercise probes, scheduler and outcome alerts.
- Approve retention/data residency; implement/rehearse authorized deletion with dependency and partial-failure handling.
- Configure encrypted paired backups; rehearse restore, RLS/role isolation, deletion replay and AI accounting; measure RPO/RTO.
- Record immutable artifacts/schema compatibility and rehearse application rollback.
- Finish live authenticated synthetic manager/player/unrelated-account tests; mocked UI tests are not deployed-boundary proof.
- Keep backups, manifests, environment contents, screenshots and private reports outside the public repository.

This change supplies documentation and a compact appearance control. Production hosting, monitors and retention/deletion implementation remain future work.
