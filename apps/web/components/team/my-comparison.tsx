"use client";
import { useLocale } from "@/components/localization/locale-provider";

import Link from "next/link";
import { useCallback } from "react";
import { ErrorState, Loading } from "@/components/ui/states";
import { useAuth } from "@/lib/auth/provider";
import { useResource } from "@/lib/data/use-resource";
import { metricLabels, type PeerComparison } from "@/lib/api/types";
import type { Locale } from "@/lib/i18n/locale";
import { metricDisplay, factDisplay } from "@/lib/format";

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

function signedMetric(value: string | null, unit: string, locale: Locale) {
  const formatted = metricDisplay(value, unit, locale);
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
  const { tr, ui, locale } = useLocale();

  const { api } = useAuth();
  const load = useCallback(
    (signal: AbortSignal) => api.myTeamComparison(teamId, reportId, signal),
    [api, teamId, reportId],
  );
  const comparison = useResource(`my-comparison:${teamId}:${reportId}`, load);
  return (
    <section className="card card-pad" aria-label={tr("You versus teammates")}>
      <div className="card-head">
        <div>
          <h2 className="section-title">{tr("You versus teammates")}</h2>
          <p className="section-subtitle">
            {compact ? tr("Latest activity ·") : ""}
            {tr("Your value is excluded from the teammate average.")}
          </p>
        </div>
        <button
          type="button"
          className="inline-link"
          onClick={comparison.refresh}
          aria-label={tr("Refresh teammate comparison")}
        >
          {tr("Refresh")}
        </button>
      </div>
      <p className="helper mb-4">
        {tr(
          "Only accepted values from this activity are included. Anonymous benchmarks require at least 5 eligible teammates per metric.",
        )}
      </p>
      {comparison.loading ? (
        <Loading label={tr("Loading your teammate comparison…")} />
      ) : comparison.error ? (
        <ErrorState message={comparison.error} onRetry={comparison.refresh} />
      ) : comparison.data ? (
        <>
          {comparison.data.status !== "ok" ? (
            <p className="info-box" role="status">
              {ui(unavailable[comparison.data.status])}
            </p>
          ) : (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              {comparison.data.metrics.map((metric) => (
                <article
                  className="rounded-xl border border-line p-4 min-w-0"
                  key={metric.metric_key}
                  aria-label={ui(metricLabels[metric.metric_key])}
                >
                  <h3 className="font-semibold text-sm">
                    {ui(metricLabels[metric.metric_key])}
                  </h3>
                  <dl className="mt-3 space-y-3 text-sm">
                    <div>
                      <dt className="helper">{tr("Your value")}</dt>
                      <dd className="text-xl font-semibold">
                        <bdi dir="ltr">
                          {metricDisplay(
                            metric.your_display_value,
                            metric.unit,
                            locale,
                          )}
                        </bdi>
                      </dd>
                    </div>
                    <div>
                      <dt className="helper">{tr("Teammate average")}</dt>
                      <dd className="font-semibold">
                        <bdi dir="ltr">
                          {metricDisplay(
                            metric.teammate_display_mean,
                            metric.unit,
                            locale,
                          )}
                        </bdi>
                      </dd>
                    </div>
                    {metric.status === "ok" && !compact && (
                      <>
                        <div>
                          <dt className="helper">{tr("Difference")}</dt>
                          <dd>
                            <bdi dir="ltr">
                              {signedMetric(
                                metric.display_absolute_difference,
                                metric.unit,
                                locale,
                              )}
                            </bdi>
                          </dd>
                        </div>
                        <div>
                          <dt className="helper">
                            {tr("Percentage difference")}
                          </dt>
                          <dd>
                            <bdi dir="ltr">
                              {metric.display_percentage_difference === null
                                ? tr("Unavailable · teammate average is zero")
                                : `${factDisplay(metric.display_percentage_difference, locale)}%`}
                            </bdi>
                          </dd>
                        </div>
                      </>
                    )}
                  </dl>
                  {metric.status === "ok" && metric.direction ? (
                    <p className="mt-3 text-sm text-muted">
                      {ui(direction[metric.direction])}
                    </p>
                  ) : (
                    <p className="helper mt-3">
                      {ui(unavailable[metric.status])}
                    </p>
                  )}
                  <p className="helper mt-2">
                    {metric.status === "not_comparable" ||
                    metric.status === "missing_metric"
                      ? tr("Eligible cohort unavailable")
                      : tr("cohortCount", {
                          count: metric.teammate_sample_size,
                        })}
                  </p>
                  {metric.metric_key === "player_load_reported" && (
                    <p className="helper mt-2">
                      {tr("Reported index · same activity only.")}
                    </p>
                  )}
                </article>
              ))}
            </div>
          )}
          <p className="helper mt-4">
            {tr(
              "Distance, high-speed distance and Player Load differences describe workload. Speed differences describe this activity, not improvement over time. ·",
            )}
            <bdi dir="auto">{comparison.data.rule_version}</bdi>
          </p>
        </>
      ) : (
        <p className="helper">{tr("Comparison unavailable.")}</p>
      )}
      {compact && (
        <Link
          className="inline-link inline-block mt-4"
          href={`/app/team/sessions/${reportId}`}
        >
          {tr("Open this activity’s comparison →")}
        </Link>
      )}
    </section>
  );
}
