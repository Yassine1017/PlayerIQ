"use client";

import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  ExternalLink,
  FileText,
  RefreshCcw,
  ShieldCheck,
} from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ChartEditor } from "@/components/uploads/chart-editor";
import { TeamImportPanel } from "@/components/uploads/team-import-panel";
import { PlayerIdentitySelection } from "@/components/identity/player-identity-selection";
import { useApp } from "@/components/layout/app-frame";
import { ErrorState, Loading, EmptyState } from "@/components/ui/states";
import { Status } from "@/components/ui/status";
import type { CandidateRow, ChartReview, SessionType } from "@/lib/api/types";
import { useAuth } from "@/lib/auth/provider";
import { useResource } from "@/lib/data/use-resource";
import { dateLabel, metricDisplay } from "@/lib/format";

function sourceValue(row: CandidateRow, label: string) {
  const found = row.metrics.find((item) => item.source_label === label);
  return found?.raw_value == null
    ? "—"
    : metricDisplay(
        found.raw_value,
        found.raw_unit ?? (label.includes("Distance") ? "m" : null),
      );
}
function chartValue(
  row: CandidateRow,
  label: string,
  metricKey: string,
  reviews: ChartReview[],
) {
  const manual = reviews.find(
    (review) =>
      review.source_athlete_row_id === row.id &&
      review.metric_key === metricKey &&
      (review.status === "confirmed" || review.status === "held"),
  );
  const automatic = row.metrics.find(
    (metric) =>
      metric.source_label === label &&
      metric.source_locator?.includes("method:"),
  );
  const value = manual?.raw_label ?? automatic?.raw_value;
  const state = manual
    ? manual.status === "held"
      ? "Needs review"
      : "Manually confirmed"
    : automatic
      ? automatic.quality_state === "accepted"
        ? "Automatically extracted"
        : "Needs review"
      : "Unavailable";
  return (
    <div>
      <span>{value ?? "—"}</span>
      <span className="block text-[10px] text-slate-500">{state}</span>
    </div>
  );
}
const processing = new Set(["received", "queued", "extracting", "validating"]);
export default function UploadReviewPage() {
  const { uploadId } = useParams<{ uploadId: string }>();
  const router = useRouter();
  const { api } = useAuth();
  const { ownedPlayer, teams, refreshIdentity } = useApp();
  const [selected, setSelected] = useState<string | null>(null);
  const [personalSelection, setPersonalSelection] = useState(false);
  const [identitySuccess, setIdentitySuccess] = useState<string | null>(null);
  const [sessionType, setSessionType] = useState<SessionType>("training");
  const [linkBusy, setLinkBusy] = useState(false);
  const [confirmIdentity, setConfirmIdentity] = useState(false);
  const [targetPlayerId, setTargetPlayerId] = useState<string | null>(null);
  const [teamToAssign, setTeamToAssign] = useState("");
  const [importType, setImportType] = useState<SessionType>("unknown");
  const [linkError, setLinkError] = useState<string | null>(null);
  const [linkedSession, setLinkedSession] = useState<string | null>(null);
  const [fileUrl, setFileUrl] = useState<string | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [fileBusy, setFileBusy] = useState(false);
  const load = useCallback(
    (signal: AbortSignal) => api.upload(uploadId, signal),
    [api, uploadId],
  );
  const status = useResource(`upload:${uploadId}`, load);
  const reportTeam = teams.find((item) => item.id === status.data?.team_id);
  const manager = reportTeam?.role === "admin" || reportTeam?.role === "coach";
  const reportTeamId = status.data?.team_id;
  const teamPlayersLoad = useCallback(
    (signal: AbortSignal) =>
      reportTeamId
        ? api.teamPlayers(reportTeamId, signal)
        : Promise.resolve({ items: [], limited_to_self: true }),
    [api, reportTeamId],
  );
  const teamPlayers = useResource(
    manager && status.data?.team_id
      ? `upload-team-players:${status.data.team_id}`
      : null,
    teamPlayersLoad,
  );
  const linkablePlayers = reportTeamId
    ? manager
      ? (teamPlayers.data?.items ?? [])
      : []
    : ownedPlayer
      ? [ownedPlayer]
      : [];
  const row = status.data?.candidate_rows.find((item) => item.id === selected);
  const defaultPlayerId = linkablePlayers.some(
    (item) => item.id === row?.recognized_player_id,
  )
    ? row?.recognized_player_id
    : linkablePlayers.some((item) => item.id === ownedPlayer?.id)
      ? ownedPlayer?.id
      : linkablePlayers[0]?.id;
  const selectedPlayerId = targetPlayerId ?? defaultPlayerId;
  const reviewLoad = useCallback(
    (signal: AbortSignal) => api.chartReviews(uploadId, signal),
    [api, uploadId],
  );
  const reviews = useResource(
    status.data?.status === "awaiting_link" ? `reviews:${uploadId}` : null,
    reviewLoad,
  );
  useEffect(() => {
    if (!status.data || !processing.has(status.data.status)) return;
    const timer = setInterval(status.refresh, 5000);
    return () => clearInterval(timer);
  }, [status.data, status.refresh]);
  useEffect(
    () => () => {
      if (fileUrl) URL.revokeObjectURL(fileUrl);
    },
    [fileUrl],
  );
  async function openFile() {
    setFileBusy(true);
    setFileError(null);
    try {
      const blob = await api.reportFile(uploadId);
      setFileUrl(URL.createObjectURL(blob));
    } catch (reason) {
      setFileError(
        reason instanceof Error ? reason.message : "File unavailable",
      );
    } finally {
      setFileBusy(false);
    }
  }
  async function link() {
    if (!row || !selectedPlayerId || !confirmIdentity) return;
    setLinkBusy(true);
    setLinkError(null);
    try {
      const chosen = selectedPlayerId;
      const recognized =
        row.recognized_player_id === chosen
          ? (row.source_identity_id ?? undefined)
          : undefined;
      const claimBody = {
        source_athlete_row_id: row.id,
        player_id: chosen,
        confirmed_source_label: row.source_name,
        session_type: sessionType,
      };
      const result = recognized
        ? await api.linkRow(uploadId, row.id, chosen, sessionType, recognized)
        : chosen === ownedPlayer?.id
          ? await api.claimSelf(uploadId, claimBody)
          : await api.confirmTeamPlayer(uploadId, claimBody);
      setLinkedSession(result.session_id);
      status.refresh();
      if (personalSelection && chosen === ownedPlayer?.id) {
        const expectedIdentityId =
          recognized ?? ("identity" in result ? result.identity.id : null);
        const verified = await api.sourceIdentities();
        if (
          !verified.items.some(
            (identity) =>
              identity.id === expectedIdentityId &&
              identity.player_id === chosen &&
              identity.status === "connected",
          )
        ) {
          throw new Error(
            "The session was linked, but your identity connection could not be confirmed. Refresh and try again.",
          );
        }
        setIdentitySuccess("Player identity connected. Opening My Dashboard…");
        await refreshIdentity();
        router.push("/app");
      }
      setConfirmIdentity(false);
    } catch (reason) {
      setLinkError(
        reason instanceof Error ? reason.message : "Could not link row",
      );
    } finally {
      setLinkBusy(false);
    }
  }
  async function assignTeam() {
    if (!teamToAssign) return;
    setLinkBusy(true);
    setLinkError(null);
    try {
      await api.requestTeamImport(uploadId, teamToAssign, importType);
      status.refresh();
    } catch (reason) {
      setLinkError(
        reason instanceof Error ? reason.message : "Could not assign team",
      );
    } finally {
      setLinkBusy(false);
    }
  }
  return (
    <div className="stack">
      <div className="page-heading">
        <div>
          <Link
            href="/app/upload"
            className="inline-link flex items-center gap-1"
          >
            <ArrowLeft size={14} /> Back to uploads
          </Link>
          <span className="eyebrow mt-4 block">
            Private report · uploader review
          </span>
          <h1 className="page-title">Report review</h1>
          <p className="page-subtitle">
            Inspect source rows and link only the athlete row you explicitly
            select.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="btn btn-quiet"
            onClick={status.refresh}
          >
            <RefreshCcw size={14} /> Refresh
          </button>
          {status.data && <Status value={status.data.status} />}
        </div>
      </div>
      {status.error ? (
        <ErrorState message={status.error.message} onRetry={status.refresh} />
      ) : status.loading && !status.data ? (
        <Loading label="Loading report status…" />
      ) : (
        status.data && (
          <>
            <div className="step-list">
              <span className="step active">
                <span className="num">1</span> Upload
              </span>
              <span
                className={`step ${status.data.status === "awaiting_link" ? "active" : ""}`}
              >
                <span className="num">2</span> Review athlete
              </span>
              <span className={`step ${row ? "active" : ""}`}>
                <span className="num">3</span> Confirm chart labels
              </span>
              <span className={`step ${linkedSession ? "active" : ""}`}>
                <span className="num">4</span> Link session
              </span>
            </div>
            <section className="card card-pad">
              <div className="card-head">
                <div>
                  <h2 className="section-title">Source report</h2>
                  <p className="section-subtitle">
                    {status.data.activity?.source_title ??
                      "Processing source metadata"}
                  </p>
                </div>
                <button
                  type="button"
                  className="btn btn-quiet"
                  disabled={fileBusy}
                  onClick={() => void openFile()}
                >
                  <FileText size={15} />
                  {fileBusy ? "Opening…" : "View private PDF"}
                </button>
              </div>
              <div className="grid gap-2 text-xs text-slate-600 sm:grid-cols-3">
                <div>
                  <span className="muted">Session date</span>
                  <strong className="block text-slate-800">
                    {dateLabel(status.data.activity?.reported_local_datetime)}
                  </strong>
                </div>
                <div>
                  <span className="muted">Activity duration</span>
                  <strong className="block text-slate-800">
                    {status.data.activity?.activity_total_time_s != null
                      ? `${status.data.activity.activity_total_time_s} seconds (report-level)`
                      : "Not reported"}
                  </strong>
                </div>
                <div>
                  <span className="muted">Extracted rows</span>
                  <strong className="block text-slate-800">
                    {status.data.candidate_rows.length}
                  </strong>
                </div>
              </div>
              {(status.data.activity?.source_team_name ||
                status.data.activity?.source_venue_name) && (
                <p className="helper mt-3 mb-0">
                  {status.data.activity.source_team_name &&
                    `Report team: ${status.data.activity.source_team_name}`}
                  {status.data.activity.source_team_name &&
                    status.data.activity.source_venue_name &&
                    " · "}
                  {status.data.activity.source_venue_name &&
                    `Venue: ${status.data.activity.source_venue_name}`}
                </p>
              )}
              {status.data.team_id ? (
                <p className="info-box mt-4">
                  Team workspace: {reportTeam?.name ?? "Assigned team"}. Only
                  accepted linked sessions appear in team analytics.
                </p>
              ) : (
                teams.some((t) => t.role !== "player") && (
                  <div className="mt-4 rounded-lg border border-slate-200 p-4">
                    <h3 className="font-bold text-sm">
                      Add this report to a team
                    </h3>
                    <p className="helper mt-1">
                      Confirming imports all identifiable athletes into the
                      selected team, including nonparticipants. Eligible
                      sessions are shared with the team. The PDF and review
                      remain private to you.
                    </p>
                    <label className="field mt-3">
                      Team
                      <select
                        className="select"
                        value={teamToAssign}
                        onChange={(e) => setTeamToAssign(e.target.value)}
                      >
                        <option value="">Select team</option>
                        {teams
                          .filter((t) => t.role !== "player")
                          .map((t) => (
                            <option key={t.id} value={t.id}>
                              {t.name}
                            </option>
                          ))}
                      </select>
                    </label>
                    <label className="field mt-3">
                      Team session type
                      <select
                        className="select"
                        value={importType}
                        onChange={(e) =>
                          setImportType(e.target.value as SessionType)
                        }
                      >
                        <option value="unknown">Unknown</option>
                        <option value="training">Training</option>
                        <option value="match">Match</option>
                      </select>
                    </label>
                    <button
                      type="button"
                      className="btn btn-quiet mt-3"
                      disabled={!teamToAssign || linkBusy}
                      onClick={() => void assignTeam()}
                    >
                      Assign team and import all athletes
                    </button>
                  </div>
                )
              )}
              {fileError && <div className="error-box mt-4">{fileError}</div>}
              {fileUrl && (
                <div className="mt-4">
                  <div className="mb-2 flex items-center justify-between">
                    <span className="helper">
                      Visible only to the uploader in this browser session
                    </span>
                    <button
                      type="button"
                      className="inline-link"
                      onClick={() => setFileUrl(null)}
                    >
                      Close preview
                    </button>
                  </div>
                  <iframe
                    title="Private GPS report preview"
                    src={fileUrl}
                    className="h-[520px] w-full rounded-lg border border-slate-200"
                  />
                  <a
                    className="inline-link mt-2 inline-flex items-center gap-1"
                    href={fileUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Open PDF in new tab <ExternalLink size={12} />
                  </a>
                </div>
              )}
            </section>
            {manager && reportTeamId && (
              <TeamImportPanel
                uploadId={uploadId}
                teamId={reportTeamId}
                players={teamPlayers.data?.items ?? []}
                onChanged={() => {
                  status.refresh();
                  teamPlayers.refresh();
                }}
              />
            )}
            {processing.has(status.data.status) && (
              <section className="card card-pad">
                <Loading
                  label={`Report is ${status.data.status}. Checking again every 5 seconds…`}
                />
                <p className="helper mt-3">
                  You can leave this page and return from Upload History.
                  Processing requires the separate backend worker to be running.
                </p>
              </section>
            )}
            {(status.data.status === "rejected" ||
              status.data.status === "failed_retryable") && (
              <section className="card card-pad">
                <div className="error-box">
                  {status.data.status === "rejected"
                    ? "This PDF could not be accepted by the supported report format."
                    : "Processing could not finish. The worker may retry; refresh this page later."}
                  {status.data.error_code
                    ? ` Code: ${status.data.error_code}`
                    : ""}
                </div>
              </section>
            )}
            {status.data.status === "awaiting_link" && (
              <>
                {ownedPlayer && (
                  <PlayerIdentitySelection
                    report={status.data}
                    playerId={ownedPlayer.id}
                    allowed={
                      !reportTeamId ||
                      Boolean(
                        manager &&
                        teamPlayers.data?.items.some(
                          (player) => player.id === ownedPlayer.id,
                        ),
                      )
                    }
                    selected={personalSelection ? (row ?? null) : null}
                    sessionType={sessionType}
                    confirmed={confirmIdentity}
                    busy={linkBusy}
                    error={linkError}
                    success={identitySuccess}
                    onSelect={(athlete) => {
                      setPersonalSelection(true);
                      setSelected(athlete.id);
                      setTargetPlayerId(ownedPlayer.id);
                      setConfirmIdentity(false);
                      setLinkedSession(null);
                      setLinkError(null);
                      setIdentitySuccess(null);
                    }}
                    onChooseAnother={() => {
                      setSelected(null);
                      setConfirmIdentity(false);
                      setLinkError(null);
                      setIdentitySuccess(null);
                    }}
                    onSessionType={setSessionType}
                    onConfirmEvidence={setConfirmIdentity}
                    onConfirm={() => void link()}
                  />
                )}
                <section className="card card-pad">
                  <div className="card-head">
                    <div>
                      <h2 className="section-title">Extracted athlete rows</h2>
                      <p className="section-subtitle">
                        Source names are evidence only. There is no automatic
                        name-based linking.
                      </p>
                    </div>
                    <span className="status info">
                      {status.data.candidate_rows.length} rows
                    </span>
                  </div>
                  {!status.data.candidate_rows.length ? (
                    <EmptyState title="No athlete rows extracted">
                      Review the validation findings below.
                    </EmptyState>
                  ) : (
                    <div className="table-wrap">
                      <table className="data-table">
                        <thead>
                          <tr>
                            <th>#</th>
                            <th>Athlete in report</th>
                            <th>Position</th>
                            <th>Distance</th>
                            <th>High-speed distance</th>
                            <th>Max velocity</th>
                            <th>Player Load</th>
                            <th>Quality</th>
                            <th>Link status</th>
                            <th>
                              <span className="sr-only">Action</span>
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          {status.data.candidate_rows.map((item) => (
                            <tr
                              key={item.id}
                              className={
                                selected === item.id ? "!bg-emerald-50" : ""
                              }
                            >
                              <td>{item.row_ordinal}</td>
                              <td className="font-bold">{item.source_name}</td>
                              <td>{item.source_position_code ?? "—"}</td>
                              <td>{sourceValue(item, "Distance (m)")}</td>
                              <td>
                                {sourceValue(item, "High Speed Distance (m)")}
                              </td>
                              <td>
                                {chartValue(
                                  item,
                                  "Maximum Velocity",
                                  "maximum_velocity_kmh",
                                  reviews.data?.items ?? [],
                                )}
                              </td>
                              <td>
                                {chartValue(
                                  item,
                                  "Player Load",
                                  "player_load_reported",
                                  reviews.data?.items ?? [],
                                )}
                              </td>
                              <td>
                                <Status value={item.quality_state} />
                              </td>
                              <td>
                                {item.links.length
                                  ? "Linked"
                                  : item.recognition_status === "recognized"
                                    ? "Recognized · confirm"
                                    : item.quality_state === "zero_recorded"
                                      ? "Zero activity"
                                      : item.quality_state !== "ready"
                                        ? "Needs review"
                                        : "Unlinked"}
                              </td>
                              <td>
                                {item.quality_state === "ready" ? (
                                  <button
                                    type="button"
                                    className="inline-link"
                                    onClick={() => {
                                      setSelected(item.id);
                                      setPersonalSelection(false);
                                      setLinkedSession(null);
                                      setConfirmIdentity(false);
                                      setTargetPlayerId(null);
                                      setLinkError(null);
                                    }}
                                  >
                                    {selected === item.id
                                      ? "Selected"
                                      : "Select row"}
                                  </button>
                                ) : (
                                  <span className="helper">
                                    {item.quality_state === "zero_recorded"
                                      ? "No activity"
                                      : "Review required"}
                                  </span>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                  {status.data.candidate_rows.some(
                    (item) => item.quality_state === "zero_recorded",
                  ) && (
                    <p className="info-box mt-4">
                      Zero recorded activity is different from a missing value.
                      Those rows cannot be linked as active player sessions.
                    </p>
                  )}
                </section>
                {row && !personalSelection && (
                  <>
                    <section className="card card-pad">
                      <div className="card-head">
                        <div>
                          <span className="eyebrow">
                            Selected athlete row #{row.row_ordinal}
                          </span>
                          <h2 className="section-title mt-2">
                            Page 2 chart values
                          </h2>
                          <p className="section-subtitle">
                            Automatically extracted labels are shown below.
                            Review uncertain values against the private source
                            PDF.
                          </p>
                        </div>
                        <ShieldCheck size={19} className="text-emerald-600" />
                      </div>
                      {reviews.error ? (
                        <ErrorState
                          message={reviews.error.message}
                          onRetry={reviews.refresh}
                        />
                      ) : reviews.loading && !reviews.data ? (
                        <Loading />
                      ) : (
                        <ChartEditor
                          uploadId={uploadId}
                          row={row}
                          reviews={reviews.data?.items ?? []}
                          onUpdate={() => {
                            reviews.refresh();
                            status.refresh();
                          }}
                        />
                      )}
                    </section>
                    <section className="card card-pad">
                      <div className="card-head">
                        <div>
                          <span className="eyebrow">
                            Confirm player identity
                          </span>
                          <h2 className="section-title mt-2">
                            {row.recognized_player_id === selectedPlayerId
                              ? "Recognized source identity"
                              : selectedPlayerId === ownedPlayer?.id
                                ? "Is this your athlete row?"
                                : "Confirm this team player's row"}
                          </h2>
                          <p className="section-subtitle">
                            Confirm the source evidence below before linking.
                            Names alone never establish an account identity.
                          </p>
                        </div>
                      </div>
                      {row.links.length > 0 && (
                        <div className="info-box mb-4">
                          This row already has a linked session. Repeating the
                          same link returns the existing session.
                        </div>
                      )}
                      {reportTeamId && manager && teamPlayers.loading ? (
                        <Loading label="Loading team players…" />
                      ) : teamPlayers.error ? (
                        <ErrorState
                          message={teamPlayers.error.message}
                          onRetry={teamPlayers.refresh}
                        />
                      ) : !linkablePlayers.length ? (
                        <div className="info-box">
                          {reportTeamId && !manager
                            ? "Team manager access is required to link this report."
                            : "No eligible player profile is available for this report."}
                        </div>
                      ) : (
                        <div className="form-row">
                          <label className="field">
                            Link to player
                            {manager ? (
                              <select
                                className="select"
                                value={selectedPlayerId ?? ""}
                                onChange={(e) => {
                                  setTargetPlayerId(e.target.value);
                                  setConfirmIdentity(false);
                                }}
                              >
                                {linkablePlayers.map((p) => (
                                  <option key={p.id} value={p.id}>
                                    {p.display_name}
                                    {p.id === ownedPlayer?.id ? " (me)" : ""}
                                  </option>
                                ))}
                              </select>
                            ) : (
                              <input
                                className="input"
                                readOnly
                                value={ownedPlayer?.display_name ?? ""}
                              />
                            )}
                          </label>
                          <label className="field">
                            Session type
                            <select
                              className="select"
                              value={sessionType}
                              onChange={(e) =>
                                setSessionType(e.target.value as SessionType)
                              }
                            >
                              <option value="training">Training</option>
                              <option value="match">Match</option>
                              <option value="unknown">Unknown</option>
                            </select>
                          </label>
                        </div>
                      )}
                      <div className="rounded-lg bg-slate-50 border border-slate-200 p-4 mt-4 text-sm">
                        <div className="grid gap-2 sm:grid-cols-2">
                          <div>
                            <span className="helper">Source athlete label</span>
                            <strong className="block">{row.source_name}</strong>
                          </div>
                          <div>
                            <span className="helper">Position</span>
                            <strong className="block">
                              {row.source_position_code ?? "Unreported"}
                            </strong>
                          </div>
                          <div>
                            <span className="helper">Session date</span>
                            <strong className="block">
                              {dateLabel(
                                status.data.activity?.reported_local_datetime,
                              )}
                            </strong>
                          </div>
                          <div>
                            <span className="helper">Quality</span>
                            <strong className="block">
                              {row.quality_state}
                            </strong>
                          </div>
                          <div>
                            <span className="helper">Distance</span>
                            <strong className="block">
                              {sourceValue(row, "Distance (m)")}
                            </strong>
                          </div>
                          <div>
                            <span className="helper">Maximum Velocity</span>
                            <strong className="block">
                              {chartValue(
                                row,
                                "Maximum Velocity",
                                "maximum_velocity_kmh",
                                reviews.data?.items ?? [],
                              )}
                            </strong>
                          </div>
                        </div>
                      </div>
                      {!linkedSession && (
                        <label className="mt-4 flex items-start gap-2 text-sm">
                          <input
                            type="checkbox"
                            className="mt-1"
                            checked={confirmIdentity}
                            onChange={(e) =>
                              setConfirmIdentity(e.target.checked)
                            }
                          />
                          <span>
                            I have checked this source row and confirm it
                            belongs to the selected player.
                          </span>
                        </label>
                      )}
                      {linkError && (
                        <div className="error-box mt-4" role="alert">
                          {linkError}
                        </div>
                      )}
                      {linkedSession ? (
                        <div className="mt-5 rounded-lg border border-emerald-200 bg-emerald-50 p-4">
                          <div className="flex items-center gap-2 text-sm font-bold text-emerald-800">
                            <CheckCircle2 size={18} /> Session linked
                          </div>
                          <div className="mt-3 flex gap-2">
                            <Link
                              href={
                                selectedPlayerId === ownedPlayer?.id
                                  ? `/app/sessions/${linkedSession}`
                                  : `/app/team/sessions/${uploadId}`
                              }
                              className="btn btn-primary"
                            >
                              View session <ArrowRight size={14} />
                            </Link>
                            <Link
                              href={
                                selectedPlayerId === ownedPlayer?.id
                                  ? "/app"
                                  : "/app/team"
                              }
                              className="btn btn-quiet"
                            >
                              Dashboard
                            </Link>
                          </div>
                        </div>
                      ) : (
                        <button
                          type="button"
                          className="btn btn-primary mt-5"
                          disabled={
                            !selectedPlayerId || linkBusy || !confirmIdentity
                          }
                          onClick={() => void link()}
                        >
                          {linkBusy
                            ? "Linking…"
                            : selectedPlayerId &&
                                selectedPlayerId !== ownedPlayer?.id
                              ? "Confirm team player link"
                              : row.recognized_player_id === selectedPlayerId
                                ? "Confirm recognized link"
                                : "This is me — confirm and link"}
                          <ArrowRight size={15} />
                        </button>
                      )}
                    </section>
                  </>
                )}
                {status.data.findings.length > 0 && (
                  <section className="card card-pad">
                    <h2 className="section-title">Validation findings</h2>
                    <ul className="mt-4 grid gap-2">
                      {status.data.findings.map((finding, index) => (
                        <li
                          key={`${finding.code}:${index}`}
                          className="text-xs text-slate-600"
                        >
                          <Status value={finding.severity} />
                          <span className="ml-2">{finding.message}</span>
                        </li>
                      ))}
                    </ul>
                  </section>
                )}
              </>
            )}
          </>
        )
      )}
    </div>
  );
}
