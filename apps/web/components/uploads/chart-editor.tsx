"use client";

import { AlertTriangle, Check, FileSearch, Pencil } from "lucide-react";
import { useState } from "react";
import type { CandidateRow, ChartReview } from "@/lib/api/types";
import { useAuth } from "@/lib/auth/provider";
import { Status } from "@/components/ui/status";

const definitions = [
  {
    key: "maximum_velocity_kmh",
    label: "Maximum Velocity",
    unit: "km/h",
    hint: "Read the exact numeric label above the athlete’s bar on page 2.",
  },
  {
    key: "player_load_reported",
    label: "Player Load",
    unit: "source index",
    hint: "The source formula and unit definition are unknown. Use the printed label exactly.",
  },
];
export function ChartEditor({
  uploadId,
  row,
  reviews,
  onUpdate,
}: {
  uploadId: string;
  row: CandidateRow;
  reviews: ChartReview[];
  onUpdate: () => void;
}) {
  return (
    <div className="grid-2-even">
      {definitions.map((definition) => (
        <ChartField
          key={`${row.id}:${definition.key}`}
          uploadId={uploadId}
          row={row}
          metricKey={definition.key}
          label={definition.label}
          unit={definition.unit}
          hint={definition.hint}
          reviews={reviews.filter(
            (item) =>
              item.source_athlete_row_id === row.id &&
              item.metric_key === definition.key,
          )}
          onUpdate={onUpdate}
        />
      ))}
    </div>
  );
}
function ChartField({
  uploadId,
  row,
  metricKey,
  label,
  unit,
  hint,
  reviews,
  onUpdate,
}: {
  uploadId: string;
  row: CandidateRow;
  metricKey: string;
  label: string;
  unit: string;
  hint: string;
  reviews: ChartReview[];
  onUpdate: () => void;
}) {
  const { api } = useAuth();
  const [raw, setRaw] = useState("");
  const [checked, setChecked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [edit, setEdit] = useState(false);
  const pending = reviews.find((item) => item.status === "proposed");
  const current = reviews.find(
    (item) => item.status === "confirmed" || item.status === "held",
  );
  const automatic = row.metrics.find(
    (item) =>
      item.source_label === label && item.source_locator?.includes("method:"),
  );
  const suspicious =
    metricKey === "maximum_velocity_kmh" &&
    Number(pending?.raw_label ?? raw) > 45;
  async function propose() {
    setBusy(true);
    setError(null);
    try {
      await api.proposeChart(uploadId, row.id, metricKey, raw.trim());
      setRaw("");
      onUpdate();
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Could not propose value",
      );
    } finally {
      setBusy(false);
    }
  }
  async function confirm() {
    if (!pending || !checked) return;
    setBusy(true);
    setError(null);
    try {
      await api.confirmChart(uploadId, pending);
      setChecked(false);
      setEdit(false);
      onUpdate();
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Could not confirm value",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="rounded-xl border border-line p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-2">
            <FileSearch size={17} className="text-accent-text" />
            <h3 className="text-sm font-bold">{label}</h3>
          </div>
          <p className="helper mt-1">Page 2 · {unit}</p>
        </div>
        {current ? (
          <Status value={current.status} />
        ) : pending ? (
          <Status value="proposed" />
        ) : automatic ? (
          <Status value={automatic.quality_state} />
        ) : (
          <Status value="missing" />
        )}
      </div>
      <p className="helper mt-3">{hint}</p>
      {current && !edit && (
        <div className="mt-4">
          <div className="text-2xl font-bold">
            {current.raw_label}{" "}
            <span className="text-xs font-normal text-muted">{unit}</span>
          </div>
          <div className="helper mt-1">
            Manually confirmed · {current.source_locator}
          </div>
          {current.status === "held" && (
            <div className="error-box mt-3">
              This value is held from analytics. Its original label is retained
              for review.
            </div>
          )}
          <button
            type="button"
            className="inline-link mt-3"
            onClick={() => setEdit(true)}
          >
            <Pencil size={12} className="inline" /> Replace printed value
          </button>
        </div>
      )}
      {!current && !pending && automatic && !edit && (
        <div className="mt-4">
          <div className="text-2xl font-bold">
            {automatic.raw_value}{" "}
            <span className="text-xs font-normal text-muted">{unit}</span>
          </div>
          <div className="helper mt-1">
            {automatic.quality_state === "accepted"
              ? "Automatically extracted"
              : "Needs review"}{" "}
            · {automatic.source_locator}
          </div>
          {automatic.quality_state !== "accepted" && (
            <div className="error-box mt-3">
              This source label is held from analytics until reviewed.
            </div>
          )}
          <button
            type="button"
            className="inline-link mt-3"
            onClick={() => setEdit(true)}
          >
            <Pencil size={12} className="inline" /> Review or correct printed
            value
          </button>
        </div>
      )}
      {(edit || (!current && (!automatic || Boolean(pending)))) && (
        <>
          {pending ? (
            <div className="mt-4">
              <div className="rounded-lg bg-surface-muted p-3">
                <div className="small muted">Proposed printed label</div>
                <div className="mt-1 text-xl font-bold">
                  {pending.raw_label}{" "}
                  <span className="text-xs font-normal text-muted">{unit}</span>
                </div>
                <div className="helper mt-1">
                  {pending.source_locator} · {pending.capture_method}
                </div>
              </div>
              {suspicious && (
                <div className="error-box mt-3 flex gap-2">
                  <AlertTriangle size={17} className="shrink-0" /> This value
                  appears unusually high and requires explicit review. It will
                  remain held from analytics if confirmed.
                </div>
              )}
              <label className="mt-3 flex items-start gap-2 text-xs leading-5">
                <input
                  type="checkbox"
                  className="mt-1 accent-emerald-600"
                  checked={checked}
                  onChange={(event) => setChecked(event.target.checked)}
                />
                <span>
                  I checked athlete row #{row.row_ordinal} and the exact printed
                  value on page 2.
                </span>
              </label>
              <button
                type="button"
                className="btn btn-primary mt-3"
                onClick={() => void confirm()}
                disabled={!checked || busy}
              >
                <Check size={15} />
                {busy ? "Confirming…" : "Confirm exact label"}
              </button>
            </div>
          ) : (
            <div className="mt-4">
              <label className="field">
                Printed numeric label
                <input
                  className="input"
                  inputMode="decimal"
                  pattern="(0|[1-9][0-9]{0,8})(\.[0-9]{1,3})?"
                  value={raw}
                  onChange={(event) => setRaw(event.target.value)}
                  placeholder={
                    metricKey === "maximum_velocity_kmh"
                      ? "e.g. 31.2"
                      : "e.g. 687"
                  }
                />
              </label>
              {suspicious && (
                <div className="error-box mt-3 flex gap-2">
                  <AlertTriangle size={17} className="shrink-0" /> This value
                  appears unusually high and requires explicit review.
                </div>
              )}
              <button
                type="button"
                className="btn btn-quiet mt-3"
                disabled={
                  !/^(0|[1-9][0-9]{0,8})(\.[0-9]{1,3})?$/.test(raw) || busy
                }
                onClick={() => void propose()}
              >
                {busy ? "Saving…" : "Propose label for confirmation"}
              </button>
            </div>
          )}
          {edit && (
            <button
              type="button"
              className="ml-3 text-xs text-muted underline"
              onClick={() => setEdit(false)}
            >
              Cancel
            </button>
          )}
        </>
      )}
      {error && (
        <div className="error-box mt-3" role="alert">
          {error}
        </div>
      )}
    </div>
  );
}
