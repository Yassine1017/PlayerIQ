"use client";
import { useLocale } from "@/components/localization/locale-provider";
import type { AnalyticsFact, PlayerSession } from "@/lib/api/types";
import { BarChart3, Gauge, Route, Zap } from "lucide-react";
import {
  comparisonCopy,
  metricDisplay,
  metricOf,
  statusText,
} from "@/lib/format";

const cards = [
  {
    key: "total_distance_m",
    label: "Total Distance",
    icon: Route,
    workload: true,
  },
  {
    key: "reported_high_speed_distance_m",
    label: "High-Speed Distance",
    icon: Zap,
    workload: true,
  },
  {
    key: "maximum_velocity_kmh",
    label: "Maximum Velocity",
    icon: Gauge,
    workload: false,
  },
  {
    key: "player_load_reported",
    label: "Player Load",
    icon: BarChart3,
    workload: true,
  },
];
export function MetricCards({
  sessions,
  facts,
}: {
  sessions: PlayerSession[];
  facts: AnalyticsFact[];
}) {
  const { tr, ui, locale } = useLocale();

  const ambiguous =
    sessions.length > 1 && sessions[0].local_date === sessions[1].local_date;
  return (
    <div className="metric-grid">
      {cards.map(({ key, label, icon: Icon, workload }) => {
        const metric = ambiguous ? null : metricOf(sessions[0], key);
        const comparison = facts.find(
          (item) =>
            item.kind === "latest_comparison" && item.metric_key === key,
        );
        const detail = ambiguous
          ? tr("Latest session order unclear")
          : metric
            ? comparisonCopy(comparison, workload, locale)
            : comparison
              ? statusText(comparison.status, locale)
              : tr("Awaiting accepted data");
        return (
          <article className="card metric-card" key={key}>
            <div className="icon-box">
              <Icon size={19} />
            </div>
            <div className="metric-label">{ui(label)}</div>
            <div className="metric-value">
              <bdi dir="ltr">
                {metric
                  ? metricDisplay(metric.value, metric.unit, locale)
                  : "—"}
              </bdi>
            </div>
            <div
              className={`metric-detail ${metric && comparison?.status === "ok" && !workload ? "positive" : ""}`}
            >
              {ui(detail)}
            </div>
          </article>
        );
      })}
    </div>
  );
}
