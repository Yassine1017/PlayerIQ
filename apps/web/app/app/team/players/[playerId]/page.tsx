"use client";

import { metricLabels } from "@/lib/api/types";
import { useLocale } from "@/components/localization/locale-provider";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback } from "react";
import { useApp } from "@/components/layout/app-frame";
import { NoTeam } from "@/components/team/team-states";
import { ErrorState, Loading } from "@/components/ui/states";
import { useAuth } from "@/lib/auth/provider";
import { useResource } from "@/lib/data/use-resource";
import { factOf, metricDisplay, statusText, analysisKind } from "@/lib/format";

export default function TeamPlayerDetailPage() {
  const { tr, ui, locale } = useLocale();

  const { playerId } = useParams<{ playerId: string }>();
  const { api } = useAuth();
  const { team } = useApp();
  const load = useCallback(
    (signal: AbortSignal) =>
      team
        ? api.teamPlayerOverview(team.id, playerId, signal)
        : Promise.resolve(null),
    [api, team, playerId],
  );
  const overview = useResource(
    team ? `team-player:${team.id}:${playerId}` : null,
    load,
  );
  const facts = overview.data?.facts ?? [];
  return (
    <div className="stack">
      <div className="page-heading">
        <div>
          <Link href="/app/team/players" className="inline-link">
            {tr("← Players")}
          </Link>
          <h1 className="page-title mt-3">{tr("Player performance")}</h1>
          <p className="page-subtitle">
            {tr(
              "Deterministic analytics from this team’s accepted sessions only.",
            )}
          </p>
        </div>
      </div>
      {!team ? (
        <NoTeam />
      ) : overview.loading ? (
        <Loading />
      ) : overview.error ? (
        <ErrorState message={overview.error} onRetry={overview.refresh} />
      ) : (
        overview.data && (
          <>
            <div className="metric-grid">
              {["maximum_velocity_kmh", "total_distance_m"].map((key) => {
                const fact = factOf(facts, "personal_record", key);
                return (
                  <div className="card card-pad" key={key}>
                    <span className="eyebrow">
                      {key === "maximum_velocity_kmh"
                        ? tr("Maximum Velocity PB")
                        : tr("Highest distance")}
                    </span>
                    <strong className="block text-2xl mt-3">
                      <bdi dir="ltr">
                        {fact?.value && fact.unit
                          ? metricDisplay(fact.value, fact.unit, locale)
                          : "—"}
                      </bdi>
                    </strong>
                    <span className="helper">
                      {fact
                        ? statusText(fact.status, locale)
                        : tr("No compatible history")}
                    </span>
                  </div>
                );
              })}
            </div>
            <section className="card card-pad">
              <h2 className="section-title">{tr("Team-scoped analytics")}</h2>
              <p className="helper mt-3">
                {tr("Rule")}
                <bdi dir="auto">{overview.data.rule_version}</bdi>
                {tr(
                  ". Each value is computed by the existing analytics service; missing or held metrics are excluded.",
                )}
              </p>
              <div className="grid gap-3 mt-4 md:grid-cols-2">
                {facts
                  .filter((f) => f.status === "ok")
                  .slice(0, 8)
                  .map((fact, index) => (
                    <div
                      key={`${fact.kind}:${fact.metric_key}:${index}`}
                      className="rounded-lg border border-line p-4"
                    >
                      <span className="helper">
                        {analysisKind(fact.kind, locale)} ·{" "}
                        {ui(metricLabels[fact.metric_key ?? ""] ?? "Session")}
                      </span>
                      <strong className="block mt-2 text-lg">
                        <bdi dir="ltr">
                          {fact.value && fact.unit
                            ? metricDisplay(fact.value, fact.unit, locale)
                            : (fact.display_value ?? "—")}
                        </bdi>
                      </strong>
                      <span className="helper">
                        {tr("n=")}
                        {fact.sample_size}
                      </span>
                    </div>
                  ))}
              </div>
            </section>
          </>
        )
      )}
    </div>
  );
}
