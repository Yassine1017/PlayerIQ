"use client";

import { useLocale } from "@/components/localization/locale-provider";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { AnalyticsFact } from "@/lib/api/types";
import { metricLabels } from "@/lib/api/types";
import { dateLabel, metricDisplay, statusText } from "@/lib/format";
import { EmptyState } from "@/components/ui/states";

export function TrendChart({ fact }: { fact: AnalyticsFact | null }) {
  const { tr, ui, locale } = useLocale();

  if (!fact)
    return (
      <EmptyState title={tr("Choose a metric")}>
        {tr("Select a metric and date range to inspect your sessions.")}
      </EmptyState>
    );
  if (!fact.points.length)
    return (
      <EmptyState title={statusText(fact.status, locale)}>
        {tr("There are no accepted, comparable values for this selection.")}
      </EmptyState>
    );
  const points = fact.points.map((point) => ({
    ...point,
    numericValue: Number(point.value),
    dateLabel: dateLabel(point.local_date, locale),
  }));
  return (
    <>
      <div
        className="chart-box"
        dir="ltr"
        role="img"
        aria-label={tr("{metric} trend for {count} sessions", {
          metric: ui(metricLabels[fact.metric_key ?? ""] ?? "Metric"),
          count: fact.points.length,
        })}
      >
        <ResponsiveContainer width="100%" height={260}>
          <LineChart
            data={points}
            margin={{ top: 18, right: 12, bottom: 4, left: -16 }}
          >
            <CartesianGrid
              stroke="var(--chart-grid)"
              strokeDasharray="3 5"
              vertical={false}
            />
            <XAxis
              dataKey="dateLabel"
              tick={{ fontSize: 10, fill: "var(--muted)" }}
              axisLine={false}
              tickLine={false}
              minTickGap={22}
            />
            <YAxis
              tick={{ fontSize: 10, fill: "var(--muted)" }}
              axisLine={false}
              tickLine={false}
              width={52}
              domain={[0, "auto"]}
            />
            <Tooltip
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const point = payload[0].payload as (typeof points)[number];
                return (
                  <div className="card px-3 py-2 text-xs shadow-lg">
                    <strong>{point.dateLabel}</strong>
                    <div>
                      <bdi dir="ltr">
                        {metricDisplay(point.value, fact.unit, locale)}
                      </bdi>
                    </div>
                    <div className="capitalize text-muted">
                      {statusText(point.session_type, locale)}
                    </div>
                  </div>
                );
              }}
            />
            <Line
              type="monotone"
              dataKey="numericValue"
              stroke="var(--chart-series)"
              strokeWidth={3}
              dot={{
                fill: "var(--surface)",
                stroke: "var(--chart-series)",
                strokeWidth: 2,
                r: 4,
              }}
              activeDot={{
                r: 6,
                fill: "var(--chart-series)",
                stroke: "var(--surface)",
              }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <details className="mt-1 text-xs text-muted">
        <summary className="cursor-pointer font-semibold">
          {tr("View accessible data table")}
        </summary>
        <div className="table-wrap mt-2">
          <table className="data-table">
            <thead>
              <tr>
                <th>{tr("Date")}</th>
                <th>{tr("Session type")}</th>
                <th>{tr("Value")}</th>
              </tr>
            </thead>
            <tbody>
              {fact.points.map((point) => (
                <tr key={point.session_id}>
                  <td>{dateLabel(point.local_date, locale)}</td>
                  <td className="capitalize">
                    {statusText(point.session_type, locale)}
                  </td>
                  <td>
                    <bdi dir="ltr">
                      {metricDisplay(point.value, fact.unit, locale)}
                    </bdi>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </>
  );
}
