"use client";
import Link from "next/link";
import { useCallback } from "react";
import { useApp } from "@/components/layout/app-frame";
import { NoTeam } from "@/components/team/team-states";
import { EmptyState, ErrorState, Loading } from "@/components/ui/states";
import { useAuth } from "@/lib/auth/provider";
import { useResource } from "@/lib/data/use-resource";
import { metricDisplay } from "@/lib/format";

export default function TeamPlayersPage() {
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
          <span className="eyebrow">Team workspace</span>
          <h1 className="page-title">Players</h1>
          <p className="page-subtitle">
            Accepted performance for player profiles visible to your team role.
          </p>
        </div>
      </div>
      {!team ? (
        <NoTeam />
      ) : players.loading ? (
        <Loading />
      ) : players.error ? (
        <ErrorState message={players.error.message} onRetry={players.refresh} />
      ) : (
        <section className="card card-pad">
          {players.data?.limited_to_self && (
            <div className="info-box mb-4">
              Your player membership shows your own performance. Coaches and
              admins may view the team directory.
            </div>
          )}
          {!players.data?.items.length ? (
            <EmptyState title="No linked player profiles yet">
              Import a GPS report into this team or approve a player account to
              build the roster.
            </EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Player</th>
                    <th>Account</th>
                    <th>Activity</th>
                    <th>Latest session</th>
                    <th>Distance</th>
                    <th>Maximum Velocity</th>
                    <th>Details</th>
                  </tr>
                </thead>
                <tbody>
                  {players.data.items.map((person) => (
                    <tr key={person.id}>
                      <td className="font-semibold">{person.display_name}</td>
                      <td>
                        {person.account_state === "unclaimed"
                          ? "Unclaimed athlete"
                          : "Registered player"}
                      </td>
                      <td>
                        {person.latest_session_date
                          ? "Accepted history"
                          : "No accepted activity"}
                      </td>
                      <td>{person.latest_session_date ?? "—"}</td>
                      {["total_distance_m", "maximum_velocity_kmh"].map(
                        (key) => {
                          const metric = person.latest_metrics.find(
                            (m) => m.metric_key === key,
                          );
                          return (
                            <td key={key}>
                              {metric
                                ? metricDisplay(metric.value, metric.unit)
                                : "—"}
                            </td>
                          );
                        },
                      )}
                      <td>
                        <Link
                          href={`/app/team/players/${person.id}`}
                          className="inline-link"
                        >
                          View →
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
