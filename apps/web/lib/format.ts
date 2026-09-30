import type {
  AnalyticsFact,
  PlayerSession,
  SessionMetric,
} from "@/lib/api/types";

export function dateLabel(date: string | null | undefined) {
  if (!date) return "Date unavailable";
  const simple = date.slice(0, 10);
  const parsed = new Date(`${simple}T12:00:00Z`);
  return Number.isNaN(parsed.getTime())
    ? date
    : new Intl.DateTimeFormat("en", {
        month: "short",
        day: "numeric",
        year: "numeric",
        timeZone: "UTC",
      }).format(parsed);
}
export function metricDisplay(
  value: string | null | undefined,
  unit: string | null | undefined,
) {
  if (value == null) return "—";
  const number = Number(value);
  if (!Number.isFinite(number)) return value;
  // Unit conversion is presentation only. All analytic calculations are returned by FastAPI.
  if (unit === "m")
    return `${new Intl.NumberFormat("en", { maximumFractionDigits: 0 }).format(number)} m`;
  if (unit === "km/h")
    return `${new Intl.NumberFormat("en", { maximumFractionDigits: 1 }).format(number)} km/h`;
  if (unit === "source units")
    return new Intl.NumberFormat("en", { maximumFractionDigits: 2 }).format(
      number,
    );
  return `${new Intl.NumberFormat("en", { maximumFractionDigits: 2 }).format(number)} ${unit ?? ""}`.trim();
}
export function metricOf(
  session: PlayerSession | null | undefined,
  key: string,
): SessionMetric | null {
  return (
    session?.metrics.find(
      (item) => item.metric_key === key && item.quality_state === "accepted",
    ) ?? null
  );
}
export function factOf(
  facts: AnalyticsFact[] | undefined,
  kind: string,
  key?: string,
) {
  return facts?.find(
    (item) =>
      item.kind === kind && (key === undefined || item.metric_key === key),
  );
}
export function statusText(status: string): string {
  return (
    (
      {
        ok: "Available",
        accepted: "Accepted",
        ready: "Ready",
        confirmed: "Confirmed",
        proposed: "Awaiting confirmation",
        held: "Held for review",
        missing: "Missing",
        missing_metric: "Metric unavailable",
        insufficient_history: "More history needed",
        not_comparable: "Not comparable",
        ambiguous_order: "Session order unclear",
        not_found: "No matching session",
        zero_recorded: "Zero activity recorded",
        needs_review: "Needs review",
        queued: "Queued",
        received: "Received",
        extracting: "Processing",
        validating: "Validating",
        awaiting_link: "Ready for review",
        rejected: "Rejected",
        failed_retryable: "Processing failed",
        high: "Higher than usual",
        low: "Lower than usual",
        normal: "Within recent range",
        insufficient_variation: "Insufficient variation",
      } as Record<string, string>
    )[status] ?? status.replaceAll("_", " ")
  );
}
export function comparisonCopy(
  fact: AnalyticsFact | undefined,
  isWorkload: boolean,
): string {
  if (!fact || fact.status !== "ok" || fact.percent_change === null)
    return fact ? statusText(fact.status) : "Comparison unavailable";
  const n = Number(fact.percent_change);
  const prefix = n > 0 ? "+" : "";
  return `${prefix}${n.toFixed(1)}% ${isWorkload ? "workload" : "speed"} vs previous ${fact.sample_size}`;
}
