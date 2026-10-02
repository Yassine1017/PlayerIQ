"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback } from "react";
import { useApp } from "@/components/layout/app-frame";
import { NoTeam } from "@/components/team/team-states";
import { ErrorState, Loading } from "@/components/ui/states";
import { metricLabels } from "@/lib/api/types";
import { useAuth } from "@/lib/auth/provider";
import { useResource } from "@/lib/data/use-resource";
import { metricDisplay } from "@/lib/format";

export default function TeamSessionDetailPage() {
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
            ← Team Sessions
          </Link>
          <h1 className="page-title mt-3">Team Session</h1>
          <p className="page-subtitle">
            Accepted participants only. Private source observations remain in
            uploader review.
          </p>
        </div>
      </div>
      {!team ? (
        <NoTeam />
      ) : detail.loading ? (
        <Loading />
      ) : detail.error ? (
        <ErrorState message={detail.error.message} onRetry={detail.refresh} />
      ) : (
        detail.data && (
          <>
            <div className="metric-grid">
              <div className="card card-pad">
                <span className="eyebrow">Date</span>
                <strong className="block text-xl mt-2">
                  {detail.data.summary.local_date}
                </strong>
              </div>
              <div className="card card-pad">
                <span className="eyebrow">Activity</span>
                <strong className="block text-xl mt-2 capitalize">
                  {detail.data.summary.session_type}
                </strong>
              </div>
              <div className="card card-pad">
                <span className="eyebrow">Participants</span>
                <strong className="block text-xl mt-2">
                  {detail.data.summary.participant_count}
                </strong>
              </div>
              <div className="card card-pad">
                <span className="eyebrow">Combined distance</span>
                <strong className="block text-xl mt-2">
                  {detail.data.summary.total_distance_m
                    ? metricDisplay(detail.data.summary.total_distance_m, "m")
                    : "—"}
                </strong>
              </div>
            </div>
            <section className="card card-pad">
              <h2 className="section-title">Accepted player performance</h2>
              {detail.data.participants.length ? (
                <div className="table-wrap mt-4">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Player</th>
                        <th>Distance</th>
                        <th>High-speed distance</th>
                        <th>Maximum Velocity</th>
                        <th>Player Load</th>
                        <th>Detail</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.data.participants.map((person) => (
                        <tr key={person.session_id}>
                          <td className="font-semibold">
                            {person.display_name}
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
                                {m ? metricDisplay(m.value, m.unit) : "—"}
                                <span className="sr-only">
                                  {" "}
                                  {metricLabels[key]}
                                </span>
                              </td>
                            );
                          })}
                          <td>
                            <Link
                              className="inline-link"
                              href={`/app/team/players/${person.player_id}`}
                            >
                              View player →
                            </Link>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="helper mt-4">
                  Participant details are limited to your own player profile.
                </p>
              )}
            </section>
          </>
        )
      )}
    </div>
  );
}
