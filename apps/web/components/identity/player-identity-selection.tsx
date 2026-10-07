"use client";
import { useLocale } from "@/components/localization/locale-provider";

import { useEffect, useRef } from "react";
import { IdentitySteps } from "./identity-onboarding";
import type { CandidateRow, SessionType, UploadStatus } from "@/lib/api/types";
import { canSelectSelf } from "@/lib/data/use-identity-reports";
import type { Locale } from "@/lib/i18n/locale";
import { dateLabel, metricDisplay } from "@/lib/format";
import { Status } from "@/components/ui/status";

function recordedDistance(row: CandidateRow, locale: Locale) {
  const distance = row.metrics.find(
    (metric) => metric.source_label === "Distance (m)",
  );
  return metricDisplay(distance?.raw_value, distance?.raw_unit ?? "m", locale);
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
  error: string | Error | null;
  success: string | null;
  onSelect: (row: CandidateRow) => void;
  onChooseAnother: () => void;
  onSessionType: (value: SessionType) => void;
  onConfirmEvidence: (value: boolean) => void;
  onConfirm: () => void;
}) {
  const { tr, ui, locale } = useLocale();

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
      <span className="eyebrow">{tr("Your player identity")}</span>
      <h2 id="select-player-heading" className="section-title mt-2">
        {tr("Select yourself from this report")}
      </h2>
      <p className="section-subtitle">
        {tr(
          "Check the source name, position and recorded distance. Your account name is never used to select an athlete.",
        )}
      </p>
      <IdentitySteps uploaded selected={Boolean(selected)} />
      {selected ? (
        <div className="identity-confirmation">
          <h3 ref={heading} tabIndex={-1} className="section-title">
            {tr("Is this your player identity?")}
          </h3>
          <dl className="identity-evidence">
            <div>
              <dt>{tr("Source athlete")}</dt>
              <dd>
                <bdi dir="auto">{selected.source_name}</bdi>
              </dd>
            </div>
            <div>
              <dt>{tr("Position")}</dt>
              <dd>{selected.source_position_code ?? tr("Not reported")}</dd>
            </div>
            <div>
              <dt>{tr("Report date")}</dt>
              <dd>
                {dateLabel(report.activity?.reported_local_datetime, locale)}
              </dd>
            </div>
            <div>
              <dt>{tr("Recorded distance")}</dt>
              <dd>
                <bdi dir="ltr">{recordedDistance(selected, locale)}</bdi>
              </dd>
            </div>
          </dl>
          <p className="helper mt-3">
            {tr(
              "Only accepted metrics will appear in your dashboard. Missing and held chart values remain unavailable.",
            )}
          </p>
          <label className="field mt-4 max-w-xs">
            {tr("Session type")}
            <select
              className="select"
              value={sessionType}
              onChange={(event) =>
                onSessionType(event.target.value as SessionType)
              }
              disabled={busy}
            >
              <option value="training">{tr("Training")}</option>
              <option value="match">{tr("Match")}</option>
              <option value="unknown">{tr("Unknown")}</option>
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
              {tr(
                "I have checked the source information and confirm this is my athlete row.",
              )}
            </span>
          </label>
          {error && (
            <div className="error-box mt-4" role="alert">
              {ui(error)}
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
              {busy ? tr("Confirming…") : tr("Confirm — This is me")}
            </button>
            <button
              type="button"
              className="btn btn-quiet"
              disabled={busy}
              onClick={onChooseAnother}
            >
              {tr("Choose another player")}
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
                ? tr(
                    "Zero activity was recorded. An accepted session cannot be created from this row.",
                  )
                : row.quality_state !== "ready"
                  ? tr(
                      "This row needs validation review before an accepted session can be created.",
                    )
                  : !canSelectSelf(row, playerId)
                    ? tr("This row is already linked to a different player.")
                    : !allowed
                      ? tr(
                          "Your player must be an active member and you must manage this assigned team report.",
                        )
                      : !report.activity?.reported_local_datetime
                        ? tr("The report date needs review before linking.")
                        : null;
            return (
              <li key={row.id} className="identity-athlete">
                <div className="min-w-0">
                  <h3 className="font-bold text-sm break-words">
                    <bdi dir="auto">{row.source_name}</bdi>
                  </h3>
                  <p className="helper mt-1">
                    {row.source_position_code ?? tr("Position not reported")} ·{" "}
                    <bdi dir="ltr">{recordedDistance(row, locale)}</bdi>{" "}
                    {tr("recorded")}
                  </p>
                  <Status value={row.quality_state} />
                  {row.recognized_player_id === playerId && (
                    <p className="helper mt-2">
                      {tr("Recognized identity · confirmation required")}
                    </p>
                  )}
                  {reason && (
                    <p className="text-xs text-muted mt-2">{ui(reason)}</p>
                  )}
                </div>
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={!eligible}
                  aria-label={tr("Select myself — {name}", {
                    name: row.source_name,
                  })}
                  onClick={() => onSelect(row)}
                >
                  {tr("Select myself →")}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
