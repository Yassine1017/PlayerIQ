"use client";

import { useLocale } from "@/components/localization/locale-provider";

import {
  Activity,
  ArrowUpRight,
  BarChart3,
  Gauge,
  Info,
  Trophy,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useState } from "react";
import { TrendChart } from "@/components/analytics/trend-chart";
import { useApp } from "@/components/layout/app-frame";
import { ErrorState, Loading, EmptyState } from "@/components/ui/states";
import { Status } from "@/components/ui/status";
import { useAuth } from "@/lib/auth/provider";
import { trendMetrics, metricLabels, type SessionType } from "@/lib/api/types";
import { useResource } from "@/lib/data/use-resource";
import {
  dateLabel,
  factOf,
  metricDisplay,
  decimalDisplay,
  statusText,
} from "@/lib/format";

function initialDates() {
  const today = new Date();
  const to = today.toISOString().slice(0, 10);
  today.setUTCFullYear(today.getUTCFullYear() - 1);
  return { from: today.toISOString().slice(0, 10), to };
}
export default function AnalyticsPage() {
  const { tr, ui, locale } = useLocale();

  const { api } = useAuth();
  const { player } = useApp();
  const [dates] = useState(initialDates);
  const [metric, setMetric] = useState<string>("maximum_velocity_kmh");
  const [from, setFrom] = useState(dates.from);
  const [to, setTo] = useState(dates.to);
  const [type, setType] = useState<SessionType>("training");
  const [applied, setApplied] = useState({
    metric: "maximum_velocity_kmh",
    from: dates.from,
    to: dates.to,
    type: "training" as SessionType,
  });
  const [outlierType, setOutlierType] = useState<"training" | "match">(
    "training",
  );
  const overviewLoad = useCallback(
    (signal: AbortSignal) => api.overview(player.id, signal),
    [api, player.id],
  );
  const overview = useResource(`analytics-overview:${player.id}`, overviewLoad);
  const trendLoad = useCallback(
    (signal: AbortSignal) =>
      api.trend(
        player.id,
        applied.metric,
        applied.from,
        applied.to,
        applied.type,
        signal,
      ),
    [api, player.id, applied],
  );
  const trend = useResource(
    `analytics-trend:${player.id}:${JSON.stringify(applied)}`,
    trendLoad,
  );
  const outlierLoad = useCallback(
    (signal: AbortSignal) => api.outliers(player.id, outlierType, 10, signal),
    [api, player.id, outlierType],
  );
  const outliers = useResource(
    `analytics-outliers:${player.id}:${outlierType}`,
    outlierLoad,
  );
  const speed = factOf(
    overview.data?.facts,
    "personal_record",
    "maximum_velocity_kmh",
  );
  const workload = factOf(
    overview.data?.facts,
    "personal_record",
    "total_distance_m",
  );
  const comparison = factOf(
    overview.data?.facts,
    "latest_comparison",
    "maximum_velocity_kmh",
  );
  const hardest = factOf(overview.data?.facts, "hardest_session");
  const t = trend.data;
  return (
    <div className="stack">
      <div className="page-heading">
        <div>
          <span className="eyebrow">{tr("Evidence-led performance")}</span>
          <h1 className="page-title">{tr("Analytics")}</h1>
          <p className="page-subtitle">
            {tr(
              "Deterministic calculations from accepted, comparable player sessions.",
            )}
          </p>
        </div>
        {overview.data && (
          <span className="status info">
            <bdi dir="auto">{overview.data.rule_version}</bdi>
          </span>
        )}
      </div>
      {overview.error ? (
        <ErrorState message={overview.error} onRetry={overview.refresh} />
      ) : overview.loading ? (
        <Loading label={tr("Loading analytics…")} />
      ) : (
        <div className="metric-grid">
          {[
            {
              title: "Latest speed vs previous 5",
              fact: comparison,
              icon: ArrowUpRight,
              description:
                comparison?.status === "ok" && comparison.percent_change != null
                  ? tr("{change}% vs {count} previous", {
                      change:
                        (comparison.percent_change.startsWith("-") ? "" : "+") +
                        decimalDisplay(comparison.percent_change, 1, locale, 1),
                      count: comparison.sample_size,
                    })
                  : comparison
                    ? statusText(comparison.status, locale)
                    : "Unavailable",
            },
            {
              title: "Maximum Velocity Record",
              fact: speed,
              icon: Gauge,
              description: "Personal best",
            },
            {
              title: "Highest Recorded Workload",
              fact: workload,
              icon: Trophy,
              description: "Total distance, not a performance score",
            },
            {
              title: "Hardest Training Session",
              fact: hardest,
              icon: Activity,
              description: "Highest confirmed training distance",
            },
          ].map((item) => (
            <div key={item.title} className="card metric-card">
              <div className="icon-box">
                <item.icon size={19} />
              </div>
              <div className="metric-label">{ui(item.title)}</div>
              <div className="metric-value">
                <bdi dir="ltr">
                  {item.fact?.status === "ok"
                    ? metricDisplay(item.fact.value, item.fact.unit, locale)
                    : "—"}
                </bdi>
              </div>
              <div className="metric-detail">
                {item.fact?.status === "ok"
                  ? ui(item.description)
                  : statusText(item.fact?.status ?? "missing", locale)}
              </div>
            </div>
          ))}
        </div>
      )}
      <section className="card card-pad">
        <div className="card-head">
          <div>
            <h2 className="section-title">{tr("Metric trend")}</h2>
            <p className="section-subtitle">
              {tr("Filter accepted sessions by metric, date, and session type")}
            </p>
          </div>
          <BarChart3 size={19} className="text-accent-text" />
        </div>
        <form
          className="grid items-end gap-3 sm:grid-cols-2 lg:grid-cols-[1.3fr_1fr_1fr_1fr_auto]"
          onSubmit={(e) => {
            e.preventDefault();
            if (from <= to) setApplied({ metric, from, to, type });
          }}
        >
          <label className="field">
            {tr("Metric")}
            <select
              className="select"
              value={metric}
              onChange={(e) => setMetric(e.target.value)}
            >
              {trendMetrics.map((key) => (
                <option key={key} value={key}>
                  {ui(metricLabels[key])}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            {tr("From")}
            <input
              className="input"
              type="date"
              required
              value={from}
              max={to}
              onChange={(e) => setFrom(e.target.value)}
            />
          </label>
          <label className="field">
            {tr("To")}
            <input
              className="input"
              type="date"
              required
              value={to}
              min={from}
              onChange={(e) => setTo(e.target.value)}
            />
          </label>
          <label className="field">
            {tr("Session type")}
            <select
              className="select"
              value={type}
              onChange={(e) => setType(e.target.value as SessionType)}
            >
              <option value="training">{tr("Training")}</option>
              <option value="match">{tr("Match")}</option>
              <option value="unknown">{tr("Unknown")}</option>
            </select>
          </label>
          <button className="btn btn-dark" type="submit">
            {tr("Apply")}
          </button>
        </form>
        <div className="mt-5 border-t border-line pt-4">
          {trend.error ? (
            <ErrorState message={trend.error} onRetry={trend.refresh} />
          ) : trend.loading ? (
            <Loading label={tr("Calculating trend…")} />
          ) : (
            <>
              <div className="mb-3 flex flex-wrap items-center gap-3">
                <Status value={t?.status ?? "missing_metric"} />
                <span className="helper">
                  {tr("sessionCount", { count: t?.sample_size ?? 0 })} ·{" "}
                  {t?.rule_version ?? "analytics_v1"}
                </span>
                {t?.status === "not_comparable" && (
                  <span className="helper">
                    {tr(
                      "Different source definitions or session types cannot be combined.",
                    )}
                  </span>
                )}
                {t?.status === "ambiguous_order" && (
                  <span className="helper">
                    {tr("Same-date sessions cannot be ordered reliably.")}
                  </span>
                )}
              </div>
              <TrendChart fact={t} />
              <div className="mt-4 grid gap-2 border-t border-line pt-4 text-xs sm:grid-cols-2 lg:grid-cols-5">
                {[
                  {
                    label: "First value",
                    value:
                      t?.status === "ok"
                        ? metricDisplay(t.baseline_value, t.unit, locale)
                        : "—",
                  },
                  {
                    label: "Latest value",
                    value:
                      t?.status === "ok"
                        ? metricDisplay(t.value, t.unit, locale)
                        : "—",
                  },
                  {
                    label: "Absolute change",
                    value:
                      t?.status === "ok"
                        ? metricDisplay(t.delta, t.unit, locale)
                        : "—",
                  },
                  {
                    label: "Percent change",
                    value:
                      t?.status === "ok" && t.percent_change != null
                        ? `${decimalDisplay(t.percent_change, 1, locale, 1)}%`
                        : "—",
                  },
                  {
                    label: "Slope per week",
                    value:
                      t?.status === "ok"
                        ? metricDisplay(t.slope_per_week, t.unit, locale)
                        : "—",
                  },
                ].map((item) => (
                  <div key={item.label}>
                    <span className="muted">{ui(item.label)}</span>
                    <strong className="mt-1 block text-sm">{item.value}</strong>
                  </div>
                ))}
              </div>
              <div className="helper mt-3">
                {tr(
                  "All changes and slope are returned by the backend. A slope requires at least three distinct session dates.",
                )}
                {t && (
                  <span className="block mt-1">
                    {tr("Source definition:")}
                    {t.definition_id ?? tr("Definition unverified")}{" "}
                    {tr("· comparison key:")}
                    {t.comparability_key ?? tr("Unavailable")}
                  </span>
                )}
              </div>
            </>
          )}
        </div>
      </section>
      <section className="card card-pad">
        <div className="card-head">
          <div>
            <h2 className="section-title">{tr("Workload outliers")}</h2>
            <p className="section-subtitle">
              {tr(
                "Unusual workload relative to recent comparable sessions, using median and MAD",
              )}
            </p>
          </div>
          <label className="field !gap-0">
            <span className="sr-only">{tr("Outlier session type")}</span>
            <select
              className="select"
              value={outlierType}
              onChange={(e) =>
                setOutlierType(e.target.value as "training" | "match")
              }
            >
              <option value="training">{tr("Training")}</option>
              <option value="match">{tr("Match")}</option>
            </select>
          </label>
        </div>
        <div className="info-box mb-4 flex gap-2">
          <Info size={17} className="shrink-0" />{" "}
          {tr(
            "This analysis describes workload variation. It is not a medical or injury assessment.",
          )}
        </div>
        {outliers.error ? (
          <ErrorState message={outliers.error} onRetry={outliers.refresh} />
        ) : outliers.loading ? (
          <Loading label={tr("Loading outliers…")} />
        ) : !outliers.data?.items.length ? (
          <EmptyState title={tr("No workload facts yet")}>
            {tr(
              "More accepted, comparable sessions are needed for outlier analysis.",
            )}
          </EmptyState>
        ) : (
          <>
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>{tr("Date")}</th>
                    <th>{tr("Metric")}</th>
                    <th>{tr("Value")}</th>
                    <th>{tr("Median")}</th>
                    <th>{tr("MAD")}</th>
                    <th>{tr("Score")}</th>
                    <th>{tr("Classification")}</th>
                    <th>{tr("Prior sample")}</th>
                  </tr>
                </thead>
                <tbody>
                  {outliers.data.items.map((item, index) => (
                    <tr
                      key={`${item.metric_key}:${item.session_ids[0] ?? index}`}
                    >
                      <td>{dateLabel(item.to_date, locale)}</td>
                      <td className="font-bold">
                        {ui(
                          metricLabels[item.metric_key ?? ""] ??
                            item.metric_key ??
                            "Metric",
                        )}
                      </td>
                      <td>
                        <bdi dir="ltr">
                          {metricDisplay(item.value, item.unit, locale)}
                        </bdi>
                      </td>
                      <td>
                        <bdi dir="ltr">
                          {metricDisplay(item.median_value, item.unit, locale)}
                        </bdi>
                      </td>
                      <td>
                        <bdi dir="ltr">
                          {metricDisplay(item.mad, item.unit, locale)}
                        </bdi>
                      </td>
                      <td>{item.score ?? "—"}</td>
                      <td>
                        <Status
                          value={
                            item.status === "ok"
                              ? (item.note ?? "ok")
                              : item.status
                          }
                        />
                        {item.note === "insufficient_variation" && (
                          <span className="helper ms-2">
                            {tr("No spread in prior values")}
                          </span>
                        )}
                      </td>
                      <td>{item.sample_size}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="helper mt-3">
              {tr("Rule")}
              <bdi dir="auto">{outliers.data.rule_version}</bdi>{" "}
              {tr(
                "· previous six sessions within 60 days · at least five comparable prior values.",
              )}{" "}
              <Link href="/app/sessions" className="inline-link">
                {tr("View sessions →")}
              </Link>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
