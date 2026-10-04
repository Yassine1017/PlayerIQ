"use client";

import Link from "next/link";
import { useCallback } from "react";
import { ErrorState, Loading } from "@/components/ui/states";
import { useAuth } from "@/lib/auth/provider";
import { useResource } from "@/lib/data/use-resource";
import { metricLabels, type PeerComparison } from "@/lib/api/types";
import { metricDisplay } from "@/lib/format";

const unavailable: Record<PeerComparison["status"], string> = {
  ok: "",
  no_player_association: "No verified player association for this team.",
  not_participating: "You have no accepted session in this activity.",
  missing_metric: "Your accepted metric is unavailable.",
  insufficient_cohort:
    "At least 5 eligible teammates are needed for this metric.",
  not_comparable: "Source definitions or participant values are incompatible.",
};
const direction = {
  above: "Above teammate average",
  below: "Below teammate average",
  equal: "Equal to teammate average",
};

function signedMetric(value: string | null, unit: string) {
  const formatted = metricDisplay(value, unit);
  return value?.startsWith("+") ? `+${formatted}` : formatted;
}

export function MyTeamComparisonPanel({
  teamId,
  reportId,
  compact = false,
}: {
  teamId: string;
  reportId: string;
  compact?: boolean;
}) {
  const { api } = useAuth();
  const load = useCallback(
    (signal: AbortSignal) => api.myTeamComparison(teamId, reportId, signal),
    [api, teamId, reportId],
  );
  const comparison = useResource(`my-comparison:${teamId}:${reportId}`, load);
  return (
    <section className="card card-pad" aria-label="You versus teammates">
      <div className="card-head">
        <div>
          <h2 className="section-title">You versus teammates</h2>
          <p className="section-subtitle">
            {compact ? "Latest activity · " : ""}Your value is excluded from the
            teammate average.
          </p>
        </div>
        <button
          type="button"
          className="inline-link"
          onClick={comparison.refresh}
          aria-label="Refresh teammate comparison"
        >
          Refresh
        </button>
      </div>
      <p className="helper mb-4">
        Only accepted values from this activity are included. Anonymous
        benchmarks require at least 5 eligible teammates per metric.
      </p>
      {comparison.loading ? (
        <Loading label="Loading your teammate comparison…" />
      ) : comparison.error ? (
        <ErrorState
          message={comparison.error.message}
          onRetry={comparison.refresh}
        />
      ) : comparison.data ? (
        <>
          {comparison.data.status !== "ok" ? (
            <p className="info-box" role="status">
              {unavailable[comparison.data.status]}
            </p>
          ) : (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              {comparison.data.metrics.map((metric) => (
                <article
                  className="rounded-xl border border-line p-4 min-w-0"
                  key={metric.metric_key}
                  aria-label={metricLabels[metric.metric_key]}
                >
                  <h3 className="font-semibold text-sm">
                    {metricLabels[metric.metric_key]}
                  </h3>
                  <dl className="mt-3 space-y-3 text-sm">
                    <div>
                      <dt className="helper">Your value</dt>
                      <dd className="text-xl font-semibold">
                        {metricDisplay(metric.your_display_value, metric.unit)}
                      </dd>
                    </div>
                    <div>
                      <dt className="helper">Teammate average</dt>
                      <dd className="font-semibold">
                        {metricDisplay(
                          metric.teammate_display_mean,
                          metric.unit,
                        )}
                      </dd>
                    </div>
                    {metric.status === "ok" && !compact && (
                      <>
                        <div>
                          <dt className="helper">Difference</dt>
                          <dd>
                            {signedMetric(
                              metric.display_absolute_difference,
                              metric.unit,
                            )}
                          </dd>
                        </div>
                        <div>
                          <dt className="helper">Percentage difference</dt>
                          <dd>
                            {metric.display_percentage_difference === null
                              ? "Unavailable · teammate average is zero"
                              : `${metric.display_percentage_difference}%`}
                          </dd>
                        </div>
                      </>
                    )}
                  </dl>
                  {metric.status === "ok" && metric.direction ? (
                    <p className="mt-3 text-sm text-muted">
                      {direction[metric.direction]}
                    </p>
                  ) : (
                    <p className="helper mt-3">{unavailable[metric.status]}</p>
                  )}
                  <p className="helper mt-2">
                    {metric.status === "not_comparable" ||
                    metric.status === "missing_metric"
                      ? "Eligible cohort unavailable"
                      : `${metric.teammate_sample_size} eligible teammates · you excluded`}
                  </p>
                  {metric.metric_key === "player_load_reported" && (
                    <p className="helper mt-2">
                      Reported index · same activity only.
                    </p>
                  )}
                </article>
              ))}
            </div>
          )}
          <p className="helper mt-4">
            Distance, high-speed distance and Player Load differences describe
            workload. Speed differences describe this activity, not improvement
            over time. · {comparison.data.rule_version}
          </p>
        </>
      ) : (
        <p className="helper">Comparison unavailable.</p>
      )}
      {compact && (
        <Link
          className="inline-link inline-block mt-4"
          href={`/app/team/sessions/${reportId}`}
        >
          Open this activity’s comparison →
        </Link>
      )}
    </section>
  );
}
