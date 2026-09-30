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
          ? "Latest session order unclear"
          : metric
            ? comparisonCopy(comparison, workload)
            : comparison
              ? statusText(comparison.status)
              : "Awaiting accepted data";
        return (
          <article className="card metric-card" key={key}>
            <div className="icon-box">
              <Icon size={19} />
            </div>
            <div className="metric-label">{label}</div>
            <div className="metric-value">
              {metric ? metricDisplay(metric.value, metric.unit) : "—"}
            </div>
            <div
              className={`metric-detail ${metric && comparison?.status === "ok" ? "positive" : ""}`}
            >
              {detail}
            </div>
          </article>
        );
      })}
    </div>
  );
}
