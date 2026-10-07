"use client";
import { statusText } from "@/lib/format";

import { useLocale } from "@/components/localization/locale-provider";
import Link from "next/link";
import type { PlayerSession } from "@/lib/api/types";
import { dateLabel, metricDisplay, metricOf } from "@/lib/format";
import { EmptyState } from "@/components/ui/states";
import { Status } from "@/components/ui/status";

export function SessionTable({ sessions }: { sessions: PlayerSession[] }) {
  const { tr, locale } = useLocale();

  if (!sessions.length)
    return (
      <EmptyState title={tr("No linked sessions yet")}>
        {tr(
          "Upload a report, review the athlete row, and link it to your player profile.",
        )}
      </EmptyState>
    );
  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>{tr("Date")}</th>
            <th>{tr("Type")}</th>
            <th>{tr("Total distance")}</th>
            <th>{tr("Maximum velocity")}</th>
            <th>{tr("Player Load")}</th>
            <th>{tr("Status")}</th>
            <th>
              <span className="sr-only">{tr("Action")}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {sessions.map((session) => (
            <tr key={session.id}>
              <td className="font-bold">
                {dateLabel(session.local_date, locale)}
              </td>
              <td className="capitalize">
                {statusText(session.session_type, locale)}
              </td>
              <td>
                <bdi dir="ltr">
                  {metricDisplay(
                    metricOf(session, "total_distance_m")?.value,
                    metricOf(session, "total_distance_m")?.unit,
                    locale,
                  )}
                </bdi>
              </td>
              <td>
                <bdi dir="ltr">
                  {metricDisplay(
                    metricOf(session, "maximum_velocity_kmh")?.value,
                    "km/h",
                    locale,
                  )}
                </bdi>
              </td>
              <td>
                <bdi dir="ltr">
                  {metricDisplay(
                    metricOf(session, "player_load_reported")?.value,
                    "source units",
                    locale,
                  )}
                </bdi>
              </td>
              <td>
                <Status value={session.quality_state} />
              </td>
              <td>
                <Link
                  href={`/app/sessions/${session.id}`}
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
  );
}
