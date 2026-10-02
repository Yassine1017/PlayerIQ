"use client";

import Link from "next/link";
import { useApp } from "@/components/layout/app-frame";
import { metricDisplay } from "@/lib/format";

export function NoTeam() {
  const { teams, teamError, refreshTeams } = useApp();
  if (teams.length) return null;
  if (teamError)
    return (
      <div className="error-box" role="alert">
        Team workspace unavailable: {teamError}{" "}
        <button
          type="button"
          className="inline-link"
          onClick={() => void refreshTeams().catch(() => undefined)}
        >
          Retry
        </button>
      </div>
    );
  return (
    <section className="card card-pad">
      <h2 className="section-title">Connect with your team</h2>
      <p className="page-subtitle mt-2">
        Create a team workspace or request to join one. Your personal
        performance stays available either way.
      </p>
      <Link href="/app/team" className="btn btn-primary mt-4">
        Set up team
      </Link>
    </section>
  );
}

export function TeamSessionCard({
  session,
}: {
  session: {
    report_upload_id: string;
    local_date: string;
    participant_count: number;
    total_distance_m: string | null;
    session_type: string;
  };
}) {
  return (
    <Link
      href={`/app/team/sessions/${session.report_upload_id}`}
      className="card card-pad block transition hover:border-emerald-300 focus-visible:outline-2 focus-visible:outline-emerald-500"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <strong className="block text-sm">
            {new Date(`${session.local_date}T12:00:00`).toLocaleDateString()}
          </strong>
          <span className="helper capitalize">
            {session.session_type} · {session.participant_count} accepted{" "}
            {session.participant_count === 1 ? "player" : "players"}
          </span>
        </div>
        <span className="text-emerald-700 text-sm font-bold">View →</span>
      </div>
      <div className="mt-4 border-t border-slate-100 pt-3 text-sm">
        {session.total_distance_m == null
          ? "Distance unavailable"
          : `${metricDisplay(session.total_distance_m, "m")} combined distance`}
      </div>
    </Link>
  );
}
