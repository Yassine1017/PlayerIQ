import Link from "next/link";
import type { PlayerSession } from "@/lib/api/types";
import { dateLabel, metricDisplay, metricOf } from "@/lib/format";
import { EmptyState } from "@/components/ui/states";
import { Status } from "@/components/ui/status";

export function SessionTable({ sessions }: { sessions: PlayerSession[] }) {
  if (!sessions.length)
    return (
      <EmptyState title="No linked sessions yet">
        Upload a report, review the athlete row, and link it to your player
        profile.
      </EmptyState>
    );
  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Type</th>
            <th>Total distance</th>
            <th>Maximum velocity</th>
            <th>Player Load</th>
            <th>Status</th>
            <th>
              <span className="sr-only">Action</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {sessions.map((session) => (
            <tr key={session.id}>
              <td className="font-bold">{dateLabel(session.local_date)}</td>
              <td className="capitalize">{session.session_type}</td>
              <td>
                {metricDisplay(
                  metricOf(session, "total_distance_m")?.value,
                  metricOf(session, "total_distance_m")?.unit,
                )}
              </td>
              <td>
                {metricDisplay(
                  metricOf(session, "maximum_velocity_kmh")?.value,
                  "km/h",
                )}
              </td>
              <td>
                {metricDisplay(
                  metricOf(session, "player_load_reported")?.value,
                  "source units",
                )}
              </td>
              <td>
                <Status value={session.quality_state} />
              </td>
              <td>
                <Link
                  href={`/app/sessions/${session.id}`}
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
  );
}
