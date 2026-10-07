import { interfaceText, translate } from "@/lib/i18n";
import type { Locale } from "@/lib/i18n/locale";
import type {
  AnalyticsFact,
  PlayerSession,
  SessionMetric,
} from "@/lib/api/types";

export function dateLabel(
  date: string | null | undefined,
  locale: Locale = "en",
) {
  if (!date) return translate(locale, "Date unavailable");
  const simple = date.slice(0, 10);
  const parsed = new Date(`${simple}T12:00:00Z`);
  return Number.isNaN(parsed.getTime()) ||
    parsed.toISOString().slice(0, 10) !== simple
    ? date
    : new Intl.DateTimeFormat(locale, {
        calendar: "gregory",
        numberingSystem: "latn",
        month: "short",
        day: "numeric",
        year: "numeric",
        timeZone: "UTC",
      }).format(parsed);
}
export function metricDisplay(
  value: string | null | undefined,
  unit: string | null | undefined,
  locale: Locale = "en",
) {
  if (value == null) return "—";
  const precision = unit === "m" ? 0 : unit === "km/h" ? 1 : 2;
  const formatted = decimalDisplay(value, precision, locale);
  return unit === "source units"
    ? formatted
    : `${formatted} ${unit ?? ""}`.trim();
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
export function statusText(status: string, locale: Locale = "en"): string {
  return interfaceText(
    locale,
    (
      {
        training: "Training",
        match: "Match",
        unknown: "Unknown",
        player: "Player",
        coach: "Coach",
        admin: "Admin",
        active: "Active",
        pending: "Pending",
        approved: "Approved",
        owned: "Owned player",
        revoked: "Revoked",
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
    )[status] ?? "Unavailable",
  );
}
export function comparisonCopy(
  fact: AnalyticsFact | undefined,
  isWorkload: boolean,
  locale: Locale = "en",
): string {
  if (!fact || fact.status !== "ok" || fact.percent_change === null)
    return fact
      ? statusText(fact.status, locale)
      : translate(locale, "Comparison unavailable");
  const prefix =
    !fact.percent_change.startsWith("-") && /[1-9]/.test(fact.percent_change)
      ? "+"
      : "";
  return translate(
    locale,
    isWorkload
      ? "{change}% workload vs previous {count}"
      : "{change}% speed vs previous {count}",
    {
      change: prefix + decimalDisplay(fact.percent_change, 1, locale, 1),
      count: fact.sample_size,
    },
  );
}

// Lossless decimal presentation: no float conversion or analytical arithmetic.
export function decimalDisplay(
  value: string,
  precision = 2,
  locale: Locale = "en",
  minimumFractionDigits = 0,
): string {
  const match = /^([+-]?)(\d+)(?:\.(\d+))?$/.exec(value);
  if (!match) return value;
  const [, sign, integer, fraction = ""] = match;
  const scale = BigInt(10) ** BigInt(precision);
  let scaled =
    BigInt(integer) * scale +
    BigInt(fraction.slice(0, precision).padEnd(precision, "0") || "0");
  if (Number(fraction[precision] ?? "0") >= 5) scaled += BigInt(1);
  const whole = scaled / scale;
  let tail = (scaled % scale)
    .toString()
    .padStart(precision, "0")
    .replace(/0+$/, "");
  tail = tail.padEnd(minimumFractionDigits, "0");
  const intl = new Intl.NumberFormat(locale, {
    numberingSystem: "latn",
    maximumFractionDigits: 0,
  });
  const separator =
    new Intl.NumberFormat(locale, { numberingSystem: "latn" })
      .formatToParts(1.1)
      .find((part) => part.type === "decimal")?.value ?? ".";
  return (
    (sign === "-" ? "-" : "") +
    intl.format(whole) +
    (tail ? separator + tail : "")
  );
}

// Preserve backend display precision, including signed facts and trailing zeros.
export function factDisplay(value: string, locale: Locale = "en"): string {
  const match = /^[-+]?\d+(?:\.(\d+))?$/.exec(value);
  if (!match) return value;
  const precision = match[1]?.length ?? 0;
  return (
    (value.startsWith("+") ? "+" : "") +
    decimalDisplay(value, precision, locale, precision)
  );
}

export function analysisKind(kind: string, locale: Locale = "en"): string {
  const labels: Record<string, string> = {
    personal_record: "Personal best",
    hardest_session: "Hardest Training Session",
    latest_comparison: "Change",
    trend: "Metric trend",
    workload_outlier: "Workload outliers",
    last_speed_exceedance: "Maximum Velocity",
    largest_change: "Change",
  };
  return interfaceText(
    locale,
    Object.hasOwn(labels, kind) ? labels[kind] : "Analysis",
  );
}
