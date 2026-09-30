# Phase 5 AI Analyst

PlayerIQ's AI Analyst is a player-scoped interpretation layer over `analytics_v1`. It uses the OpenAI Responses API for semantic function selection and concise prose. PostgreSQL and the existing pure analytics domain remain the only source of numerical GPS results. The browser never receives the OpenAI key or raw provider SDK objects.

## Request path

1. FastAPI verifies the Supabase JWT, authorizes the player and private thread/session, checks the daily run quota, and reserves an idempotent `ai_runs` row with the accepted-history fingerprint. A chat user message is inserted in the same transaction.
2. The provider receives a bounded question, a few prior **user** questions marked untrusted, and strict read-only tool definitions. `OpenAIProvider` is behind an injectable `AIProvider` protocol; tests use a fake provider and need no network or key. Responses requests use `store=false`, a bounded timeout/output, and no hosted web, code, or file tools.
3. Each requested tool is validated with a closed Pydantic argument model. FastAPI rechecks authorization and the fingerprint before executing a tool through `AnalyticsService`. There is no AI arithmetic path. Rejected calls are recorded with a safe error code rather than raw arguments.
4. The run-local `FactRegistry` gives deterministic values IDs, Decimal strings, display values, units, `analytics_v1`, metric definition/comparability, sample size, and source session/observation IDs. Only bounded results go to the provider. Unsupported or missing results keep their explicit status.
5. A second Responses call requests a strict structured answer. The server rejects authored numbers/units, fake fact IDs, invalid session citations, medical claims, and workload-only improvement claims. One bounded corrective attempt is permitted. A failed validation or provider error produces an explicit unavailable answer; facts remain separately inspectable.
6. The validated answer, bounded evidence snapshot, provider/model identity, usage where available, audit records with source observation IDs, and completion status are saved. On every read, the current accepted-history fingerprint is compared to the run's fingerprint. A later chart correction marks the old answer stale and the UI offers regeneration.

Official implementation references checked on 2026-09-30: [Responses function calling](https://developers.openai.com/api/docs/guides/function-calling), [structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs), [conversation state and `store=false`](https://developers.openai.com/api/docs/guides/conversation-state), and the [Python SDK](https://developers.openai.com/api/docs/libraries). PlayerIQ keeps its own bounded chat context instead of a provider Conversation object. Streaming is deferred because the answer is shown only after grounding validation.

## Supported tools

`get_latest_session_comparison`, `get_metric_trend`, `get_personal_records`, `get_hardest_session`, `get_last_speed_exceedance`, `get_largest_change`, `get_workload_outliers`, and `get_session_facts` call existing Phase 3 domain/service methods. Metric names are allowlisted. A model argument never selects a player. Session facts come only from accepted, explicitly linked history for the authorized player. Player Load has unknown units/formula and cannot support cross-session comparison until its definition is verified; workload quantities are never automatically called performance improvement. The “hardest” default is highest total distance among confirmed training sessions, a workload proxy rather than physiological difficulty.

## Privacy, limits, and retry policy

`0006_ai_analyst` adds an analytics rule version and actor/player idempotency key to existing `ai_runs` and grants narrow API-role access under forced RLS. Chat threads/messages are creator-private. AI runs and tool audits are actor-private and require current player access. An active coach grant permits that coach's own chat; revocation blocks subsequent reads and tool calls. A linked player never gains the uploader's team report or teammate rows through AI.

Settings in `.env.example` bound question/context length, tool count, result facts, response length, date range, provider timeout/attempts, and new runs per actor per day. A repeated request ID returns a completed run without a second provider call. The same ID with changed chat content or another thread is a conflict. A still-pending ID returns `analysis_in_progress`; after an uncertain server crash, the client must not silently retry with a new ID because that could duplicate provider charges. Provider calls are not made within an open database transaction. Logs contain run/tool/status/timing metadata, never JWTs, API keys, raw reports, or full chat text.

## UI and verification limits

`/app/analyst` provides suggested questions, creator-private conversation history, a question composer, verified fact cards, source links, statuses, stale notices, and a “How calculated” panel. Accepted session detail offers a separate session-analysis action. The AI prose is labeled as interpretation; displayed numbers are resolved from the backend fact registry.

Committed tests use only synthetic data and fake provider responses. They check tool schemas, grounding failures, privacy, idempotency, audit, confirmed-speed evidence, and staleness after a chart correction. A real OpenAI call was not made because no development `OPENAI_API_KEY` was configured. Authenticated browser E2E remains a manual **PlayerIQ Dev** check until a confirmed development Auth account is available. Apply migration `0006` before that check, then use only synthetic history and a minimal paid call.
