"use client";

import { useLocale } from "@/components/localization/locale-provider";

import {
  ArrowRight,
  ClipboardCheck,
  Sparkles,
  Trophy,
  UploadCloud,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useState } from "react";
import { TrendChart } from "@/components/analytics/trend-chart";
import { MetricCards } from "@/components/dashboard/metric-card";
import { IdentityOnboarding } from "@/components/identity/identity-onboarding";
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
  const { tr, ui, locale } = useLocale();

  const { api } = useAuth();
  const { player, team } = useApp();
  const [metric, setMetric] = useState<string>("total_distance_m");
  const [range] = useState(windowDates);
  const loadOverview = useCallback(
    (signal: AbortSignal) => api.overview(player.id, signal),
    [api, player.id],
  );
  const loadIdentities = useCallback(
    (signal: AbortSignal) => api.sourceIdentities(signal),
    [api],
  );
  const identities = useResource(
    `dashboard-identities:${player.id}`,
    loadIdentities,
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
  const connected =
    identities.data?.items.some(
      (item) => item.player_id === player.id && item.status === "connected",
    ) ?? false;
  return (
    <div className="stack">
      <div className="hero">
        <div className="hero-content">
          <span className="eyebrow">
            {tr("My Dashboard · personal performance")}
          </span>
          <h1>
            {tr("Welcome back, {name}", {
              name: player.display_name.split(" ")[0],
            })}
            .
          </h1>
          <p>
            {tr(
              "Your reviewed GPS data, clear records, and session trends in one place.",
            )}
          </p>
          <p className="mt-2 text-sm">
            {sessions.data?.items[0]
              ? tr("Latest accepted session: {date}", {
                  date: dateLabel(sessions.data.items[0].local_date, locale),
                })
              : sessions.loading
                ? tr("Loading latest session…")
                : tr("No accepted session yet")}
            {team ? ` · ${team.name}` : ""}
          </p>
          <Link href="/app/upload" className="btn btn-primary mt-3">
            {tr("Upload a report")}
            <ArrowRight size={15} className="directional-icon" />
          </Link>
        </div>
      </div>
      {identities.error ? (
        <ErrorState message={identities.error} onRetry={identities.refresh} />
      ) : identities.loading ? (
        <Loading label={tr("Checking your GPS identity…")} />
      ) : identities.data && !connected ? (
        <IdentityOnboarding />
      ) : null}
      {connected &&
        !sessions.loading &&
        !sessions.error &&
        sessions.data?.items.length === 0 && (
          <div className="info-box">
            <strong>{tr("Your GPS identity is connected")}</strong>
            <p className="mt-1 text-sm">
              {tr(
                "No accepted GPS history is available yet. Review a report and confirm an eligible session to start your performance history.",
              )}
            </p>
            <Link href="/app/upload" className="inline-link mt-2 inline-block">
              {tr("Review reports →")}
            </Link>
          </div>
        )}
      {overview.error ? (
        <ErrorState message={overview.error} onRetry={overview.refresh} />
      ) : sessions.error ? (
        <ErrorState message={sessions.error} onRetry={sessions.refresh} />
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
              <h2 className="section-title">{tr("Performance trend")}</h2>
              <p className="section-subtitle">
                {tr("Accepted training sessions · last six months")}
              </p>
            </div>
            <label className="field !gap-0 w-[170px] shrink-0">
              <span className="sr-only">{tr("Trend metric")}</span>
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
          </div>
          {trend.error ? (
            <ErrorState message={trend.error} onRetry={trend.refresh} />
          ) : trend.loading ? (
            <Loading label={tr("Loading trend…")} />
          ) : (
            <>
              <TrendChart fact={trend.data} />
              <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-line pt-3 text-xs text-muted">
                <span>
                  {trend.data
                    ? statusText(trend.data.status, locale)
                    : tr("Unavailable")}{" "}
                  ·{" "}
                  {tr("sessionCount", { count: trend.data?.sample_size ?? 0 })}
                </span>
                <Link href="/app/analytics" className="inline-link">
                  {tr("Explore analytics →")}
                </Link>
              </div>
            </>
          )}
        </section>
        <section className="card card-pad">
          <div className="card-head">
            <div>
              <h2 className="section-title">{tr("Recorded highlights")}</h2>
              <p className="section-subtitle">
                {tr("Backed by accepted player history")}
              </p>
            </div>
            <Trophy size={18} className="text-accent-text" />
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
                      <div className="text-xs font-bold">
                        {ui(record.label)}
                      </div>
                      <div className="small muted">
                        {ui(record.sub)}
                        {fact?.to_date
                          ? ` · ${dateLabel(fact.to_date, locale)}`
                          : ""}
                      </div>
                    </div>
                    <div className="text-end">
                      <strong>
                        <bdi dir="ltr">
                          {fact?.status === "ok"
                            ? metricDisplay(fact.value, fact.unit, locale)
                            : "—"}
                        </bdi>
                      </strong>
                      {fact?.status !== "ok" && (
                        <div className="small muted">
                          {fact
                            ? statusText(fact.status, locale)
                            : tr("Unavailable")}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
              <div className="info-box mt-4">
                {tr(
                  "Player Load is a source-reported workload index. Its formula and unit definition are not yet verified.",
                )}
              </div>
            </>
          )}
        </section>
      </div>
      <div className="grid-2">
        <section className="card card-pad">
          <div className="card-head">
            <div>
              <h2 className="section-title">{tr("Recent sessions")}</h2>
              <p className="section-subtitle">
                {tr("Your accepted, explicitly linked player sessions")}
              </p>
            </div>
            <Link href="/app/sessions" className="inline-link">
              {tr("View all →")}
            </Link>
          </div>
          {sessions.loading ? (
            <Loading />
          ) : sessions.error ? (
            <ErrorState message={sessions.error} onRetry={sessions.refresh} />
          ) : (
            <SessionTable sessions={sessions.data?.items ?? []} />
          )}
        </section>
        <section className="card card-pad">
          <div className="card-head">
            <div>
              <h2 className="section-title">{tr("Your next step")}</h2>
              <p className="section-subtitle">
                {tr("Keep your history current")}
              </p>
            </div>
            <ClipboardCheck size={18} className="text-accent-text" />
          </div>
          <div className="rounded-xl border border-line bg-accent-soft p-5">
            <UploadCloud className="text-accent-text" size={25} />
            <h3 className="mt-3 text-sm font-bold">{tr("Add a GPS report")}</h3>
            <p className="text-xs leading-5 text-muted">
              {tr(
                "Upload a supported PDF, inspect the extracted athlete rows, then choose and link your own row. Review chart-only values when automatic extraction is uncertain.",
              )}
            </p>
            <Link href="/app/upload" className="btn btn-primary mt-2">
              {tr("Upload report")}
              <ArrowRight size={15} className="directional-icon" />
            </Link>
          </div>
          <div className="mt-4 rounded-xl border border-line bg-surface-muted p-5">
            <Sparkles className="text-info-text" size={25} />
            <h3 className="mt-3 text-sm font-bold">
              {tr("Ask the AI Analyst")}
            </h3>
            <p className="text-xs leading-5 text-muted">
              {tr(
                "Explore your accepted history with answers grounded in deterministic analytics. Opening the page does not start an AI request.",
              )}
            </p>
            <Link href="/app/analyst" className="btn btn-quiet mt-2">
              {tr("Open Analyst")}
              <ArrowRight size={15} className="directional-icon" />
            </Link>
          </div>
        </section>
      </div>
    </div>
  );
}
