"use client";

import { useEffect, useRef } from "react";
import { IdentitySteps } from "./identity-onboarding";
import type { CandidateRow, SessionType, UploadStatus } from "@/lib/api/types";
import { canSelectSelf } from "@/lib/data/use-identity-reports";
import { dateLabel, metricDisplay } from "@/lib/format";
import { Status } from "@/components/ui/status";

function recordedDistance(row: CandidateRow) {
  const distance = row.metrics.find(
    (metric) => metric.source_label === "Distance (m)",
  );
  return metricDisplay(distance?.raw_value, distance?.raw_unit ?? "m");
}

export function PlayerIdentitySelection({
  report,
  playerId,
  allowed,
  selected,
  sessionType,
  confirmed,
  busy,
  error,
  success,
  onSelect,
  onChooseAnother,
  onSessionType,
  onConfirmEvidence,
  onConfirm,
}: {
  report: UploadStatus;
  playerId: string;
  allowed: boolean;
  selected: CandidateRow | null;
  sessionType: SessionType;
  confirmed: boolean;
  busy: boolean;
  error: string | null;
  success: string | null;
  onSelect: (row: CandidateRow) => void;
  onChooseAnother: () => void;
  onSessionType: (value: SessionType) => void;
  onConfirmEvidence: (value: boolean) => void;
  onConfirm: () => void;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  const selectedId = selected?.id;
  useEffect(() => {
    if (selectedId) {
      heading.current?.focus({ preventScroll: true });
      heading.current?.scrollIntoView?.({ behavior: "smooth", block: "start" });
    }
  }, [selectedId]);
  return (
    <section
      id="player-identity"
      className="card card-pad identity-selection"
      aria-labelledby="select-player-heading"
    >
      <span className="eyebrow">Your player identity</span>
      <h2 id="select-player-heading" className="section-title mt-2">
        Select yourself from this report
      </h2>
      <p className="section-subtitle">
        Check the source name, position and recorded distance. Your account name
        is never used to select an athlete.
      </p>
      <IdentitySteps uploaded selected={Boolean(selected)} />
      {selected ? (
        <div className="identity-confirmation">
          <h3 ref={heading} tabIndex={-1} className="section-title">
            Is this your player identity?
          </h3>
          <dl className="identity-evidence">
            <div>
              <dt>Source athlete</dt>
              <dd>{selected.source_name}</dd>
            </div>
            <div>
              <dt>Position</dt>
              <dd>{selected.source_position_code ?? "Not reported"}</dd>
            </div>
            <div>
              <dt>Report date</dt>
              <dd>{dateLabel(report.activity?.reported_local_datetime)}</dd>
            </div>
            <div>
              <dt>Recorded distance</dt>
              <dd>{recordedDistance(selected)}</dd>
            </div>
          </dl>
          <p className="helper mt-3">
            Only accepted metrics will appear in your dashboard. Missing and
            held chart values remain unavailable.
          </p>
          <label className="field mt-4 max-w-xs">
            Session type
            <select
              className="select"
              value={sessionType}
              onChange={(event) =>
                onSessionType(event.target.value as SessionType)
              }
              disabled={busy}
            >
              <option value="training">Training</option>
              <option value="match">Match</option>
              <option value="unknown">Unknown</option>
            </select>
          </label>
          <label className="mt-4 flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              className="mt-1"
              checked={confirmed}
              disabled={busy}
              onChange={(event) => onConfirmEvidence(event.target.checked)}
            />
            <span>
              I have checked the source information and confirm this is my
              athlete row.
            </span>
          </label>
          {error && (
            <div className="error-box mt-4" role="alert">
              {error}
            </div>
          )}
          {success && (
            <div className="info-box mt-4" role="status">
              {success}
            </div>
          )}
          <div className="identity-actions mt-4">
            <button
              type="button"
              className="btn btn-primary"
              disabled={!confirmed || busy}
              onClick={onConfirm}
            >
              {busy ? "Confirming…" : "Confirm — This is me"}
            </button>
            <button
              type="button"
              className="btn btn-quiet"
              disabled={busy}
              onClick={onChooseAnother}
            >
              Choose another player
            </button>
          </div>
        </div>
      ) : (
        <ul className="identity-athletes">
          {report.candidate_rows.map((row) => {
            const eligible =
              allowed &&
              Boolean(report.activity?.reported_local_datetime) &&
              canSelectSelf(row, playerId);
            const reason =
              row.quality_state === "zero_recorded"
                ? "Zero activity was recorded. An accepted session cannot be created from this row."
                : row.quality_state !== "ready"
                  ? "This row needs validation review before an accepted session can be created."
                  : !canSelectSelf(row, playerId)
                    ? "This row is already linked to a different player."
                    : !allowed
                      ? "Your player must be an active member and you must manage this assigned team report."
                      : !report.activity?.reported_local_datetime
                        ? "The report date needs review before linking."
                        : null;
            return (
              <li key={row.id} className="identity-athlete">
                <div className="min-w-0">
                  <h3 className="font-bold text-sm break-words">
                    {row.source_name}
                  </h3>
                  <p className="helper mt-1">
                    {row.source_position_code ?? "Position not reported"} ·{" "}
                    {recordedDistance(row)} recorded
                  </p>
                  <Status value={row.quality_state} />
                  {row.recognized_player_id === playerId && (
                    <p className="helper mt-2">
                      Recognized identity · confirmation required
                    </p>
                  )}
                  {reason && (
                    <p className="text-xs text-muted mt-2">{reason}</p>
                  )}
                </div>
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={!eligible}
                  aria-label={`Select myself — ${row.source_name}`}
                  onClick={() => onSelect(row)}
                >
                  Select myself →
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
