"use client";
import { useLocale } from "@/components/localization/locale-provider";

import {
  ArrowLeft,
  CheckCircle2,
  FileClock,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { AnswerCard } from "@/components/analyst/answer-card";
import type { AnalystResponse } from "@/lib/api/types";
import { useApp } from "@/components/layout/app-frame";
import { ErrorState, Loading, EmptyState } from "@/components/ui/states";
import { Status } from "@/components/ui/status";
import { useAuth } from "@/lib/auth/provider";
import { ApiError } from "@/lib/api/client";
import { useResource } from "@/lib/data/use-resource";
import { dateLabel, metricDisplay, metricOf, statusText } from "@/lib/format";
import { metricLabels } from "@/lib/api/types";

const primary = [
  "total_distance_m",
  "reported_high_speed_distance_m",
  "maximum_velocity_kmh",
  "player_load_reported",
];
export default function SessionDetail() {
  const { tr, ui, locale } = useLocale();

  const { sessionId } = useParams<{ sessionId: string }>();
  const { api } = useAuth();
  const { player } = useApp();
  const load = useCallback(
    (signal: AbortSignal) => api.session(player.id, sessionId, signal),
    [api, player.id, sessionId],
  );
  const resource = useResource(`session:${player.id}:${sessionId}`, load);
  const session = resource.data;
  return (
    <div className="stack">
      <div className="page-heading">
        <div>
          <Link
            href="/app/sessions"
            className="inline-link flex items-center gap-1"
          >
            <ArrowLeft size={14} className="directional-icon" />{" "}
            {tr("Back to sessions")}
          </Link>
          <span className="eyebrow mt-4 block">
            {tr("Accepted player history")}
          </span>
          <h1 className="page-title">
            {tr("Session ·")}
            {dateLabel(session?.local_date, locale)}
          </h1>
          <p className="page-subtitle capitalize">
            {session
              ? statusText(session.session_type, locale)
              : tr("Loading session")}{" "}
            · <bdi dir="auto">{player.display_name}</bdi>
          </p>
        </div>
        {session && <Status value={session.quality_state} />}
      </div>
      {resource.error ? (
        <ErrorState
          message={
            resource.error instanceof ApiError && resource.error.status === 404
              ? tr("This session is unavailable to this account.")
              : resource.error
          }
          onRetry={resource.refresh}
        />
      ) : resource.loading && !session ? (
        <Loading label={tr("Loading session details…")} />
      ) : (
        session && (
          <>
            <div className="metric-grid">
              {primary.map((key) => {
                const metric = metricOf(session, key);
                return (
                  <div className="card metric-card" key={key}>
                    <div className="metric-label">{ui(metricLabels[key])}</div>
                    <div className="metric-value mt-4">
                      <bdi dir="ltr">
                        {metric
                          ? metricDisplay(metric.value, metric.unit, locale)
                          : "—"}
                      </bdi>
                    </div>
                    <div className="metric-detail">
                      {metric
                        ? tr("Accepted value")
                        : tr("Not available in this session")}
                    </div>
                  </div>
                );
              })}
            </div>
            <div className="detail-grid">
              <section className="card card-pad">
                <div className="card-head">
                  <div>
                    <h2 className="section-title">{tr("Accepted metrics")}</h2>
                    <p className="section-subtitle">
                      {tr("Exact stored values and their reported units")}
                    </p>
                  </div>
                  <CheckCircle2 size={19} className="text-accent-text" />
                </div>
                {session.metrics.length ? (
                  <div className="table-wrap">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>{tr("Metric")}</th>
                          <th>{tr("Value")}</th>
                          <th>{tr("Report label")}</th>
                          <th>{tr("Quality")}</th>
                          <th>{tr("Source definition")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {session.metrics.map((item) => (
                          <tr key={item.metric_key}>
                            <td className="font-bold">
                              {metricLabels[item.metric_key] ??
                                item.source_label}
                            </td>
                            <td>
                              <bdi dir="ltr">
                                {metricDisplay(item.value, item.unit, locale)}
                              </bdi>
                            </td>
                            <td>
                              <bdi dir="auto">{item.source_label}</bdi>
                            </td>
                            <td>
                              <Status value={item.quality_state} />
                            </td>
                            <td>
                              {item.definition_id ??
                                tr("Definition unverified")}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <EmptyState title={tr("No accepted metrics")}>
                    {tr(
                      "Held or missing values are excluded from the accepted metric list.",
                    )}
                  </EmptyState>
                )}
              </section>
              <div className="stack">
                <section className="card card-pad">
                  <div className="card-head">
                    <h2 className="section-title">
                      {tr("Source & provenance")}
                    </h2>
                    <ShieldCheck size={18} className="text-accent-text" />
                  </div>
                  <div className="key-value">
                    <span>{tr("Report reference")}</span>
                    <strong className="font-mono text-[10px]">
                      <bdi dir="auto">
                        {session.provenance.report_upload_id}
                      </bdi>
                    </strong>
                  </div>
                  <div className="key-value">
                    <span>{tr("Athlete row reference")}</span>
                    <strong className="font-mono text-[10px]">
                      <bdi dir="auto">
                        {session.provenance.source_athlete_row_id}
                      </bdi>
                    </strong>
                  </div>
                  <p className="helper mt-3">
                    {tr(
                      "This session contains only the linked athlete’s accepted values. The full team PDF remains private to its uploader.",
                    )}
                  </p>
                </section>
                <section className="card card-pad">
                  <div className="card-head">
                    <h2 className="section-title">{tr("Validation notes")}</h2>
                    <FileClock size={18} className="text-info-text" />
                  </div>
                  {session.warnings.length ? (
                    <ul className="grid gap-3">
                      {session.warnings.map((item, index) => (
                        <li
                          key={`${item.code}:${index}`}
                          className="text-xs leading-5 text-muted"
                        >
                          <Status value={item.severity} />{" "}
                          <span className="ms-1">
                            <bdi dir="auto">{item.message}</bdi>
                          </span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="helper mb-0">
                      {tr("No validation warnings on this accepted session.")}
                    </p>
                  )}
                </section>
              </div>
            </div>
            <SessionAnalysis
              key={`${player.id}:${sessionId}`}
              playerId={player.id}
              sessionId={sessionId}
            />
          </>
        )
      )}
    </div>
  );
}

function SessionAnalysis({
  playerId,
  sessionId,
}: {
  playerId: string;
  sessionId: string;
}) {
  const { tr, ui } = useLocale();

  const { api } = useAuth();
  const [result, setResult] = useState<AnalystResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | Error | null>(null);
  useEffect(() => {
    let active = true;
    api
      .sessionAnalysis(playerId, sessionId)
      .then((analysis) => {
        if (active) setResult(analysis);
      })
      .catch((reason) => {
        if (active && !(reason instanceof ApiError && reason.status === 404))
          setError(
            reason instanceof Error ? reason : "Could not load analysis",
          );
      });
    return () => {
      active = false;
    };
  }, [api, playerId, sessionId]);
  async function generate() {
    setLoading(true);
    setError(null);
    try {
      setResult(
        await api.analyzeSession(playerId, sessionId, crypto.randomUUID()),
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason : "Analysis unavailable");
    } finally {
      setLoading(false);
    }
  }
  return (
    <section
      className="card card-pad stack"
      aria-label={tr("Session AI analysis")}
    >
      <div className="card-head">
        <div>
          <span className="eyebrow">{tr("PlayerIQ Analyst")}</span>
          <h2 className="section-title">{tr("Session interpretation")}</h2>
          <p className="section-subtitle">
            {tr(
              "An explanation of verified facts from this session and your history.",
            )}
          </p>
        </div>
        <Sparkles size={19} className="text-accent-text" />
      </div>
      {result && <AnswerCard result={result} />}
      {error && <ErrorState message={ui(error)} />}
      <button
        type="button"
        className="btn btn-primary self-start"
        onClick={() => void generate()}
        disabled={loading}
      >
        {loading
          ? tr("Analyzing your history…")
          : result?.stale
            ? tr("Regenerate current analysis")
            : result
              ? tr("Analyze again")
              : tr("Analyze this session")}
      </button>
    </section>
  );
}
