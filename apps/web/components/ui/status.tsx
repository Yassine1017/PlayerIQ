import { statusText } from "@/lib/format";

const good = new Set([
  "accepted",
  "ready",
  "confirmed",
  "ok",
  "awaiting_link",
  "normal",
]);
const warn = new Set([
  "needs_review",
  "zero_recorded",
  "proposed",
  "insufficient_history",
  "not_comparable",
  "ambiguous_order",
  "failed_retryable",
  "low",
  "insufficient_variation",
]);
const bad = new Set(["held", "rejected", "missing_metric", "high"]);
export function Status({ value }: { value: string }) {
  const tone = good.has(value)
    ? "good"
    : warn.has(value)
      ? "warn"
      : bad.has(value)
        ? "bad"
        : ["queued", "extracting", "validating", "received"].includes(value)
          ? "info"
          : "";
  return <span className={`status ${tone}`}>{statusText(value)}</span>;
}
