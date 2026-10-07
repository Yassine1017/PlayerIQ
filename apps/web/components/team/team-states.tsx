"use client";
import { statusText } from "@/lib/format";

import { useLocale } from "@/components/localization/locale-provider";

import Link from "next/link";
import { useApp } from "@/components/layout/app-frame";
import { dateLabel, metricDisplay } from "@/lib/format";
import type { TeamSession } from "@/lib/api/types";

export function NoTeam() {
  const { tr, ui } = useLocale();

  const { teams, teamError, refreshTeams } = useApp();
  if (teams.length) return null;
  if (teamError)
    return (
      <div className="error-box" role="alert">
        {tr("Team workspace unavailable:")}
        {ui(teamError)}{" "}
        <button
          type="button"
          className="inline-link"
          onClick={() => void refreshTeams().catch(() => undefined)}
        >
          {tr("Retry")}
        </button>
      </div>
    );
  return (
    <section className="card card-pad">
      <h2 className="section-title">{tr("Connect with your team")}</h2>
      <p className="page-subtitle mt-2">
        {tr(
          "Create a team workspace or request to join one. Your personal performance stays available either way.",
        )}
      </p>
      <Link href="/app/team" className="btn btn-primary mt-4">
        {tr("Set up team")}
      </Link>
    </section>
  );
}

export function TeamSessionCard({ session }: { session: TeamSession }) {
  const { tr, locale } = useLocale();

  return (
    <Link
      href={`/app/team/sessions/${session.report_upload_id}`}
      className="card card-pad block transition hover:border-accent-text focus-visible:outline-2 focus-visible:outline-accent-text"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <strong className="block text-sm">
            {dateLabel(session.local_date, locale)}
          </strong>
          <span className="helper capitalize">
            {statusText(session.session_type, locale)} ·{" "}
            {tr("participantCount", { count: session.participant_count })}
          </span>
        </div>
        <span className="text-accent-text text-sm font-bold">
          {tr("View →")}
        </span>
      </div>
      <div className="mt-4 border-t border-line pt-3 text-sm">
        {session.average_distance ? (
          <div className="space-y-2">
            <p>
              {tr("Average distance:")}{" "}
              <bdi dir="ltr">
                {session.average_distance.status === "ok"
                  ? metricDisplay(session.average_distance.value, "m", locale)
                  : "—"}
              </bdi>
              <span className="helper block">
                {session.average_distance.sample_size}{" "}
                {tr("accepted players with distance")}
              </span>
            </p>
            <p>
              {tr("Average Player Load:")}{" "}
              <bdi dir="ltr">
                {session.average_player_load?.status === "ok"
                  ? metricDisplay(
                      session.average_player_load.value,
                      session.average_player_load.unit,
                      locale,
                    )
                  : "—"}
              </bdi>
              <span className="helper block">
                {session.average_player_load?.sample_size ?? 0}{" "}
                {tr("accepted players · reported index, same activity")}
              </span>
            </p>
          </div>
        ) : session.total_distance_m == null ? (
          tr("Distance unavailable")
        ) : (
          tr("{value} combined distance", {
            value: metricDisplay(session.total_distance_m, "m", locale),
          })
        )}
      </div>
    </Link>
  );
}
