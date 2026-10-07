"use client";
import { useLocale } from "@/components/localization/locale-provider";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback } from "react";
import { useApp } from "@/components/layout/app-frame";
import { NoTeam } from "@/components/team/team-states";
import { MyTeamComparisonPanel } from "@/components/team/my-comparison";
import { ErrorState, Loading } from "@/components/ui/states";
import { metricLabels } from "@/lib/api/types";
import { useAuth } from "@/lib/auth/provider";
import { useResource } from "@/lib/data/use-resource";
import { metricDisplay, statusText, dateLabel } from "@/lib/format";

export default function TeamSessionDetailPage() {
  const { tr, ui, locale } = useLocale();

  const { reportId } = useParams<{ reportId: string }>();
  const { api } = useAuth();
  const { team } = useApp();
  const load = useCallback(
    (signal: AbortSignal) =>
      team ? api.teamSession(team.id, reportId, signal) : Promise.resolve(null),
    [api, team, reportId],
  );
  const detail = useResource(
    team ? `team-session:${team.id}:${reportId}` : null,
    load,
  );
  return (
    <div className="stack">
      <div className="page-heading">
        <div>
          <Link href="/app/team/sessions" className="inline-link">
            {tr("← Team Sessions")}
          </Link>
          <h1 className="page-title mt-3">{tr("Team Session")}</h1>
          <p className="page-subtitle">
            {tr(
              "Accepted participants only. Private source observations remain in uploader review.",
            )}
          </p>
        </div>
      </div>
      {!team ? (
        <NoTeam />
      ) : detail.loading ? (
        <Loading />
      ) : detail.error ? (
        <ErrorState message={detail.error} onRetry={detail.refresh} />
      ) : (
        detail.data && (
          <>
            <div className="metric-grid">
              <div className="card card-pad">
                <span className="eyebrow">{tr("Date")}</span>
                <strong className="block text-xl mt-2">
                  {dateLabel(detail.data.summary.local_date, locale)}
                </strong>
              </div>
              <div className="card card-pad">
                <span className="eyebrow">{tr("Activity")}</span>
                <strong className="block text-xl mt-2 capitalize">
                  {statusText(detail.data.summary.session_type, locale)}
                </strong>
              </div>
              <div className="card card-pad">
                <span className="eyebrow">{tr("Participants")}</span>
                <strong className="block text-xl mt-2">
                  {detail.data.summary.participant_count}
                </strong>
              </div>
              <div className="card card-pad">
                <span className="eyebrow">{tr("Combined distance")}</span>
                <strong className="block text-xl mt-2">
                  <bdi dir="ltr">
                    {detail.data.summary.total_distance_m
                      ? metricDisplay(
                          detail.data.summary.total_distance_m,
                          "m",
                          locale,
                        )
                      : "—"}
                  </bdi>
                </strong>
              </div>
            </div>
            <section className="card card-pad">
              <h2 className="section-title">
                {tr("Accepted player performance")}
              </h2>
              {detail.data.participants.length ? (
                <div className="table-wrap mt-4">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>{tr("Player")}</th>
                        <th>{tr("Distance")}</th>
                        <th>{tr("High-speed distance")}</th>
                        <th>{tr("Maximum Velocity")}</th>
                        <th>{tr("Player Load")}</th>
                        <th>{tr("Detail")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.data.participants.map((person) => (
                        <tr key={person.session_id}>
                          <td className="font-semibold">
                            <bdi dir="auto">{person.display_name}</bdi>
                          </td>
                          {[
                            "total_distance_m",
                            "reported_high_speed_distance_m",
                            "maximum_velocity_kmh",
                            "player_load_reported",
                          ].map((key) => {
                            const m = person.metrics.find(
                              (value) => value.metric_key === key,
                            );
                            return (
                              <td key={key}>
                                <bdi dir="ltr">
                                  {m
                                    ? metricDisplay(m.value, m.unit, locale)
                                    : "—"}
                                </bdi>
                                <span className="sr-only">
                                  {" "}
                                  {ui(metricLabels[key])}
                                </span>
                              </td>
                            );
                          })}
                          <td>
                            <Link
                              className="inline-link"
                              href={`/app/team/players/${person.player_id}`}
                            >
                              {tr("View player →")}
                            </Link>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="helper mt-4">
                  {tr(
                    "Participant details are limited to your own player profile.",
                  )}
                </p>
              )}
            </section>
            <MyTeamComparisonPanel
              key={`${team.id}:${reportId}`}
              teamId={team.id}
              reportId={reportId}
            />
          </>
        )
      )}
    </div>
  );
}
