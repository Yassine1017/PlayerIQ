"use client";

import { ArrowRight, ClipboardCheck, Trophy, UploadCloud } from "lucide-react";
import Link from "next/link";
import { useCallback, useState } from "react";
import { TrendChart } from "@/components/analytics/trend-chart";
import { MetricCards } from "@/components/dashboard/metric-card";
import { useApp } from "@/components/layout/app-frame";
import { SessionTable } from "@/components/sessions/session-table";
import { ErrorState, Loading } from "@/components/ui/states";
import { useAuth } from "@/lib/auth/provider";
import { trendMetrics, metricLabels } from "@/lib/api/types";
import { dateLabel, factOf, metricDisplay, statusText } from "@/lib/format";
import { useResource } from "@/lib/data/use-resource";

function windowDates() {
  const now = new Date();
  const to = now.toISOString().slice(0, 10);
  now.setUTCMonth(now.getUTCMonth() - 6);
  return { from: now.toISOString().slice(0, 10), to };
}
export default function Dashboard() {
  const { api } = useAuth();
  const { player } = useApp();
  const [metric, setMetric] = useState<string>("total_distance_m");
  const [range] = useState(windowDates);
  const loadOverview = useCallback(
    (signal: AbortSignal) => api.overview(player.id, signal),
    [api, player.id],
  );
  const loadSessions = useCallback(
    (signal: AbortSignal) => api.sessions(player.id, 5, undefined, signal),
    [api, player.id],
  );
  const loadTrend = useCallback(
    (signal: AbortSignal) =>
      api.trend(player.id, metric, range.from, range.to, "training", signal),
    [api, player.id, metric, range],
  );
  const overview = useResource(`overview:${player.id}`, loadOverview);
  const sessions = useResource(`sessions:${player.id}`, loadSessions);
  const trend = useResource(
    `trend:${player.id}:${metric}:${range.from}`,
    loadTrend,
  );
  return (
    <div className="stack">
      <div className="hero">
        <div className="hero-content">
          <span className="eyebrow">Your performance workspace</span>
          <h1>Welcome back, {player.display_name.split(" ")[0]}.</h1>
          <p>
            Your reviewed GPS data, clear records, and session trends in one
            place.
          </p>
          <Link href="/app/upload" className="btn btn-primary mt-3">
            Upload a report <ArrowRight size={15} />
          </Link>
        </div>
      </div>
      {overview.error ? (
        <ErrorState
          message={overview.error.message}
          onRetry={overview.refresh}
        />
      ) : sessions.error ? (
        <ErrorState
          message={sessions.error.message}
          onRetry={sessions.refresh}
        />
      ) : overview.loading || sessions.loading ? (
        <div className="metric-grid">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="card card-pad">
              <div className="skeleton h-24" />
            </div>
          ))}
        </div>
      ) : (
        <MetricCards
          sessions={sessions.data?.items ?? []}
          facts={overview.data?.facts ?? []}
        />
      )}
      <div className="grid-2">
        <section className="card card-pad">
          <div className="card-head">
            <div>
              <h2 className="section-title">Performance trend</h2>
              <p className="section-subtitle">
                Accepted training sessions · last six months
              </p>
            </div>
            <label className="field !gap-0 w-[170px] shrink-0">
              <span className="sr-only">Trend metric</span>
              <select
                className="select"
                value={metric}
                onChange={(e) => setMetric(e.target.value)}
              >
                {trendMetrics.map((key) => (
                  <option key={key} value={key}>
                    {metricLabels[key]}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {trend.error ? (
            <ErrorState message={trend.error.message} onRetry={trend.refresh} />
          ) : trend.loading ? (
            <Loading label="Loading trend…" />
          ) : (
            <>
              <TrendChart fact={trend.data} />
              <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-3 text-xs text-slate-500">
                <span>
                  {trend.data ? statusText(trend.data.status) : "Unavailable"} ·{" "}
                  {trend.data?.sample_size ?? 0} sessions
                </span>
                <Link href="/app/analytics" className="inline-link">
                  Explore analytics →
                </Link>
              </div>
            </>
          )}
        </section>
        <section className="card card-pad">
          <div className="card-head">
            <div>
              <h2 className="section-title">Recorded highlights</h2>
              <p className="section-subtitle">
                Backed by accepted player history
              </p>
            </div>
            <Trophy size={18} className="text-emerald-500" />
          </div>
          {overview.loading ? (
            <Loading />
          ) : (
            <>
              {[
                {
                  key: "maximum_velocity_kmh",
                  label: "Maximum Velocity",
                  sub: "Personal best",
                },
                {
                  key: "total_distance_m",
                  label: "Highest Recorded Workload",
                  sub: "Total distance",
                },
              ].map((record) => {
                const fact = factOf(
                  overview.data?.facts,
                  "personal_record",
                  record.key,
                );
                return (
                  <div className="record-row" key={record.key}>
                    <div className="record-icon">
                      <Trophy size={17} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-xs font-bold">{record.label}</div>
                      <div className="small muted">
                        {record.sub}
                        {fact?.to_date ? ` · ${dateLabel(fact.to_date)}` : ""}
                      </div>
                    </div>
                    <div className="text-right">
                      <strong>
                        {fact?.status === "ok"
                          ? metricDisplay(fact.value, fact.unit)
                          : "—"}
                      </strong>
                      {fact?.status !== "ok" && (
                        <div className="small muted">
                          {fact ? statusText(fact.status) : "Unavailable"}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
              <div className="info-box mt-4">
                Player Load is a source-reported workload index. Its formula and
                unit definition are not yet verified.
              </div>
            </>
          )}
        </section>
      </div>
      <div className="grid-2">
        <section className="card card-pad">
          <div className="card-head">
            <div>
              <h2 className="section-title">Recent sessions</h2>
              <p className="section-subtitle">
                Your accepted, explicitly linked player sessions
              </p>
            </div>
            <Link href="/app/sessions" className="inline-link">
              View all →
            </Link>
          </div>
          {sessions.loading ? (
            <Loading />
          ) : sessions.error ? (
            <ErrorState
              message={sessions.error.message}
              onRetry={sessions.refresh}
            />
          ) : (
            <SessionTable sessions={sessions.data?.items ?? []} />
          )}
        </section>
        <section className="card card-pad">
          <div className="card-head">
            <div>
              <h2 className="section-title">Your next step</h2>
              <p className="section-subtitle">Keep your history current</p>
            </div>
            <ClipboardCheck size={18} className="text-emerald-500" />
          </div>
          <div className="rounded-xl border border-emerald-100 bg-emerald-50 p-5">
            <UploadCloud className="text-emerald-600" size={25} />
            <h3 className="mt-3 text-sm font-bold">Add a GPS report</h3>
            <p className="text-xs leading-5 text-slate-600">
              Upload a supported PDF, inspect the extracted athlete rows, then
              choose and link your own row. Chart-only values require your
              confirmation.
            </p>
            <Link href="/app/upload" className="btn btn-primary mt-2">
              Upload report <ArrowRight size={15} />
            </Link>
          </div>
        </section>
      </div>
    </div>
  );
}
