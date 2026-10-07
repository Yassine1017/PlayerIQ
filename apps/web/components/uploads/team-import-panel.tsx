"use client";
import { useLocale } from "@/components/localization/locale-provider";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/lib/auth/provider";
import { ApiError } from "@/lib/api/client";
import type { SessionType, TeamImportRow, TeamPlayer } from "@/lib/api/types";
import { useResource } from "@/lib/data/use-resource";
import { Loading, ErrorState } from "@/components/ui/states";

export const importOutcomeLabels: Record<string, string> = {
  accepted_session: "Accepted session created",
  existing_session: "Existing session reused",
  no_activity: "No recorded activity · roster only",
  identity_review: "Identity review required",
  metric_review: "Metric review required · roster only",
  session_conflict: "Session conflict · review required",
};

export function TeamImportPanel({
  uploadId,
  teamId,
  players,
  onChanged,
}: {
  uploadId: string;
  teamId: string;
  players: TeamPlayer[];
  onChanged: () => void;
}) {
  const { tr, ui } = useLocale();

  const { api } = useAuth();
  const [type, setType] = useState<SessionType>("unknown");
  const [share, setShare] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | Error | null>(null);
  const [selected, setSelected] = useState<TeamImportRow | null>(null);
  const [target, setTarget] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const load = useCallback(
    async (signal: AbortSignal) => {
      try {
        return await api.teamImport(uploadId, signal);
      } catch (reason) {
        if (reason instanceof ApiError && reason.code === "import_not_found")
          return null;
        throw reason;
      }
    },
    [api, uploadId],
  );
  const result = useResource(`team-import:${uploadId}`, load);
  useEffect(() => {
    if (result.data?.status !== "queued") return;
    const timer = setInterval(result.refresh, 5000);
    return () => clearInterval(timer);
  }, [result.data?.status, result.refresh]);
  async function request() {
    setBusy(true);
    setError(null);
    try {
      await api.requestTeamImport(
        uploadId,
        teamId,
        result.data?.session_type ?? type,
      );
      result.refresh();
      onChanged();
    } catch (reason) {
      setError(
        reason instanceof Error ? reason : "Import could not be requested",
      );
    } finally {
      setBusy(false);
    }
  }
  async function resolve() {
    if (!selected || !confirmed) return;
    setBusy(true);
    setError(null);
    try {
      await api.resolveTeamImport(
        uploadId,
        selected.row_id,
        target || null,
        selected.source_name,
      );
      setSelected(null);
      result.refresh();
      onChanged();
    } catch (reason) {
      setError(
        reason instanceof Error ? reason : "Association could not be confirmed",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="card card-pad" aria-label={tr("Team roster import")}>
      <h2 className="section-title">{tr("Team roster import")}</h2>
      <p className="helper">
        {tr(
          "All identifiable athletes join the roster, including nonparticipants. Only eligible metrics enter accepted sessions. Account access requires a separate verified association.",
        )}
      </p>
      {result.loading ? (
        <Loading />
      ) : result.error ? (
        <ErrorState message={result.error} onRetry={result.refresh} />
      ) : !result.data ? (
        <>
          <label className="field">
            {tr("Session type")}
            <select
              className="select"
              value={type}
              onChange={(e) => setType(e.target.value as SessionType)}
            >
              <option value="unknown">{tr("Unknown")}</option>
              <option value="training">{tr("Training")}</option>
              <option value="match">{tr("Match")}</option>
            </select>
          </label>
          <label className="mt-4 flex gap-2 text-sm">
            <input
              type="checkbox"
              checked={share}
              onChange={(e) => setShare(e.target.checked)}
            />
            {tr(
              "I authorize importing every athlete into this team and sharing accepted sessions. The PDF and private review remain visible only to me.",
            )}
          </label>
          <button
            className="btn btn-primary mt-4"
            disabled={!share || busy}
            onClick={() => void request()}
          >
            {tr("Import all athletes")}
          </button>
        </>
      ) : (
        <>
          <div className="info-box mt-4" role="status">
            {result.data.status === "queued"
              ? tr("Roster import queued. Waiting for processing…")
              : result.data.status === "failed"
                ? tr("Import failed. Retry after the issue is resolved.")
                : result.data.status === "needs_review"
                  ? tr("Import finished with rows needing review.")
                  : tr("Roster import complete.")}
            <p className="mb-0 mt-2">
              {tr(
                "{athletes} athletes · {profiles} new profiles · {sessions} accepted sessions · {inactive} with no recorded activity",
                {
                  athletes: result.data.counts.total ?? 0,
                  profiles: result.data.counts.created_players ?? 0,
                  sessions: result.data.counts.accepted_sessions ?? 0,
                  inactive: result.data.counts.no_activity ?? 0,
                },
              )}
            </p>
          </div>
          <button className="btn btn-quiet mt-3" onClick={result.refresh}>
            {tr("Refresh import")}
          </button>
          {result.data.status === "failed" && (
            <button
              className="btn btn-primary mt-3 ms-2"
              disabled={busy}
              onClick={() => void request()}
            >
              {tr("Retry import")}
            </button>
          )}
          {!!result.data.rows.length && (
            <div className="table-wrap mt-4">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>{tr("Athlete")}</th>
                    <th>{tr("Association")}</th>
                    <th>{tr("Result")}</th>
                    <th>{tr("Review")}</th>
                  </tr>
                </thead>
                <tbody>
                  {result.data.rows.map((row) => (
                    <tr key={row.row_id}>
                      <td>
                        <bdi dir="auto">{row.source_name}</bdi>
                      </td>
                      <td>
                        {row.association_method === "manager_confirmed"
                          ? tr("Verified athlete association")
                          : row.created_player
                            ? tr("Imported unclaimed athlete")
                            : row.association_method === "unresolved"
                              ? tr("Unresolved")
                              : tr("Existing player reused")}
                      </td>
                      <td>
                        {ui(
                          importOutcomeLabels[row.outcome] ?? "Review required",
                        )}
                      </td>
                      <td>
                        <button
                          className="inline-link"
                          onClick={() => {
                            setSelected(row);
                            setTarget(row.player_id ?? "");
                            setConfirmed(false);
                          }}
                        >
                          {tr("Review association")}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
      {selected && (
        <div className="mt-4 rounded-lg border border-line p-4">
          <h3 className="section-title">
            {tr("Confirm athlete:")}
            <bdi dir="auto">{selected.source_name}</bdi>
          </h3>
          <p className="helper">
            {tr(
              "Confirm the source row belongs to the selected athlete. Connecting an unclaimed athlete to an approved account moves its team history to that account, preserving sessions. Conflicting dates require review.",
            )}
          </p>
          <label className="field">
            {tr("Roster athlete")}
            <select
              className="select"
              value={target}
              onChange={(e) => {
                setTarget(e.target.value);
                setConfirmed(false);
              }}
            >
              <option value="">
                {selected.player_id
                  ? tr("Keep current athlete")
                  : tr("Create separate unclaimed athlete")}
              </option>
              {players.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.display_name} ·{" "}
                  {p.account_state === "unclaimed"
                    ? tr("Unclaimed")
                    : tr("Approved account")}
                </option>
              ))}
            </select>
          </label>
          <label className="mt-3 flex gap-2 text-sm">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
            />
            {tr("I verified this source row and athlete association.")}
          </label>
          <button
            className="btn btn-primary mt-3"
            disabled={!confirmed || busy}
            onClick={() => void resolve()}
          >
            {tr("Confirm athlete association")}
          </button>
          <button
            className="btn btn-quiet ms-2 mt-3"
            onClick={() => setSelected(null)}
          >
            {tr("Cancel")}
          </button>
        </div>
      )}
      {error && (
        <div className="error-box mt-4" role="alert">
          {ui(error)}
        </div>
      )}
    </section>
  );
}
