"use client";
import { useLocale } from "@/components/localization/locale-provider";
import Link from "next/link";
import { useCallback } from "react";
import { useApp } from "@/components/layout/app-frame";
import { NoTeam } from "@/components/team/team-states";
import { EmptyState, ErrorState, Loading } from "@/components/ui/states";
import { useAuth } from "@/lib/auth/provider";
import { useResource } from "@/lib/data/use-resource";
import { metricDisplay } from "@/lib/format";

export default function TeamPlayersPage() {
  const { tr, locale } = useLocale();

  const { api } = useAuth();
  const { team } = useApp();
  const load = useCallback(
    (signal: AbortSignal) =>
      team
        ? api.teamPlayers(team.id, signal)
        : Promise.resolve({ items: [], limited_to_self: true }),
    [api, team],
  );
  const players = useResource(team ? `team-players:${team.id}` : null, load);
  return (
    <div className="stack">
      <div className="page-heading">
        <div>
          <span className="eyebrow">{tr("Team workspace")}</span>
          <h1 className="page-title">{tr("Players")}</h1>
          <p className="page-subtitle">
            {tr(
              "Accepted performance for player profiles visible to your team role.",
            )}
          </p>
        </div>
      </div>
      {!team ? (
        <NoTeam />
      ) : players.loading ? (
        <Loading />
      ) : players.error ? (
        <ErrorState message={players.error} onRetry={players.refresh} />
      ) : (
        <section className="card card-pad">
          {players.data?.limited_to_self && (
            <div className="info-box mb-4">
              {tr(
                "Your player membership shows your own performance. Coaches and admins may view the team directory.",
              )}
            </div>
          )}
          {!players.data?.items.length ? (
            <EmptyState title={tr("No linked player profiles yet")}>
              {tr(
                "Import a GPS report into this team or approve a player account to build the roster.",
              )}
            </EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>{tr("Player")}</th>
                    <th>{tr("Account")}</th>
                    <th>{tr("Activity")}</th>
                    <th>{tr("Latest session")}</th>
                    <th>{tr("Distance")}</th>
                    <th>{tr("Maximum Velocity")}</th>
                    <th>{tr("Details")}</th>
                  </tr>
                </thead>
                <tbody>
                  {players.data.items.map((person) => (
                    <tr key={person.id}>
                      <td className="font-semibold">
                        <bdi dir="auto">{person.display_name}</bdi>
                      </td>
                      <td>
                        {person.account_state === "unclaimed"
                          ? tr("Unclaimed athlete")
                          : tr("Registered player")}
                      </td>
                      <td>
                        {person.latest_session_date
                          ? tr("Accepted history")
                          : tr("No accepted activity")}
                      </td>
                      <td>{person.latest_session_date ?? "—"}</td>
                      {["total_distance_m", "maximum_velocity_kmh"].map(
                        (key) => {
                          const metric = person.latest_metrics.find(
                            (m) => m.metric_key === key,
                          );
                          return (
                            <td key={key}>
                              <bdi dir="ltr">
                                {metric
                                  ? metricDisplay(
                                      metric.value,
                                      metric.unit,
                                      locale,
                                    )
                                  : "—"}
                              </bdi>
                            </td>
                          );
                        },
                      )}
                      <td>
                        <Link
                          href={`/app/team/players/${person.id}`}
                          className="inline-link"
                        >
                          {tr("View →")}
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
