"use client";

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
  if (!fact)
    return (
      <EmptyState title="Choose a metric">
        Select a metric and date range to inspect your sessions.
      </EmptyState>
    );
  if (!fact.points.length)
    return (
      <EmptyState title={statusText(fact.status)}>
        There are no accepted, comparable values for this selection.
      </EmptyState>
    );
  const points = fact.points.map((point) => ({
    ...point,
    numericValue: Number(point.value),
    dateLabel: dateLabel(point.local_date),
  }));
  return (
    <>
      <div
        className="chart-box"
        role="img"
        aria-label={`${metricLabels[fact.metric_key ?? ""] ?? "Metric"} trend for ${fact.points.length} sessions`}
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
                    <div>{metricDisplay(point.value, fact.unit)}</div>
                    <div className="capitalize text-muted">
                      {point.session_type}
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
          View accessible data table
        </summary>
        <div className="table-wrap mt-2">
          <table className="data-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Session type</th>
                <th>Value</th>
              </tr>
            </thead>
            <tbody>
              {fact.points.map((point) => (
                <tr key={point.session_id}>
                  <td>{dateLabel(point.local_date)}</td>
                  <td className="capitalize">{point.session_type}</td>
                  <td>{metricDisplay(point.value, fact.unit)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </>
  );
}
