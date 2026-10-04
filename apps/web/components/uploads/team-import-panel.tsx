"use client";

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
  const { api } = useAuth();
  const [type, setType] = useState<SessionType>("unknown");
  const [share, setShare] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
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
        reason instanceof Error
          ? reason.message
          : "Import could not be requested",
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
        reason instanceof Error
          ? reason.message
          : "Association could not be confirmed",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="card card-pad" aria-label="Team roster import">
      <h2 className="section-title">Team roster import</h2>
      <p className="helper">
        All identifiable athletes join the roster, including nonparticipants.
        Only eligible metrics enter accepted sessions. Account access requires a
        separate verified association.
      </p>
      {result.loading ? (
        <Loading />
      ) : result.error ? (
        <ErrorState message={result.error.message} onRetry={result.refresh} />
      ) : !result.data ? (
        <>
          <label className="field">
            Session type
            <select
              className="select"
              value={type}
              onChange={(e) => setType(e.target.value as SessionType)}
            >
              <option value="unknown">Unknown</option>
              <option value="training">Training</option>
              <option value="match">Match</option>
            </select>
          </label>
          <label className="mt-4 flex gap-2 text-sm">
            <input
              type="checkbox"
              checked={share}
              onChange={(e) => setShare(e.target.checked)}
            />
            I authorize importing every athlete into this team and sharing
            accepted sessions. The PDF and private review remain visible only to
            me.
          </label>
          <button
            className="btn btn-primary mt-4"
            disabled={!share || busy}
            onClick={() => void request()}
          >
            Import all athletes
          </button>
        </>
      ) : (
        <>
          <div className="info-box mt-4" role="status">
            {result.data.status === "queued"
              ? "Roster import queued. Waiting for processing…"
              : result.data.status === "failed"
                ? "Import failed. Retry after the issue is resolved."
                : result.data.status === "needs_review"
                  ? "Import finished with rows needing review."
                  : "Roster import complete."}
            <p className="mb-0 mt-2">
              {result.data.counts.total ?? 0} athletes ·{" "}
              {result.data.counts.created_players ?? 0} new profiles ·{" "}
              {result.data.counts.accepted_sessions ?? 0} accepted sessions ·{" "}
              {result.data.counts.no_activity ?? 0} with no recorded activity
            </p>
          </div>
          <button className="btn btn-quiet mt-3" onClick={result.refresh}>
            Refresh import
          </button>
          {result.data.status === "failed" && (
            <button
              className="btn btn-primary mt-3 ml-2"
              disabled={busy}
              onClick={() => void request()}
            >
              Retry import
            </button>
          )}
          {!!result.data.rows.length && (
            <div className="table-wrap mt-4">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Athlete</th>
                    <th>Association</th>
                    <th>Result</th>
                    <th>Review</th>
                  </tr>
                </thead>
                <tbody>
                  {result.data.rows.map((row) => (
                    <tr key={row.row_id}>
                      <td>{row.source_name}</td>
                      <td>
                        {row.association_method === "manager_confirmed"
                          ? "Verified athlete association"
                          : row.created_player
                            ? "Imported unclaimed athlete"
                            : row.association_method === "unresolved"
                              ? "Unresolved"
                              : "Existing player reused"}
                      </td>
                      <td>
                        {importOutcomeLabels[row.outcome] ?? "Review required"}
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
                          Review association
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
            Confirm athlete: {selected.source_name}
          </h3>
          <p className="helper">
            Confirm the source row belongs to the selected athlete. Connecting
            an unclaimed athlete to an approved account moves its team history
            to that account, preserving sessions. Conflicting dates require
            review.
          </p>
          <label className="field">
            Roster athlete
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
                  ? "Keep current athlete"
                  : "Create separate unclaimed athlete"}
              </option>
              {players.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.display_name} ·{" "}
                  {p.account_state === "unclaimed"
                    ? "Unclaimed"
                    : "Approved account"}
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
            I verified this source row and athlete association.
          </label>
          <button
            className="btn btn-primary mt-3"
            disabled={!confirmed || busy}
            onClick={() => void resolve()}
          >
            Confirm athlete association
          </button>
          <button
            className="btn btn-quiet ml-2 mt-3"
            onClick={() => setSelected(null)}
          >
            Cancel
          </button>
        </div>
      )}
      {error && (
        <div className="error-box mt-4" role="alert">
          {error}
        </div>
      )}
    </section>
  );
}
