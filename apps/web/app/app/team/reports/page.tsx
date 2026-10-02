"use client";
import { useCallback } from "react";
import { useApp } from "@/components/layout/app-frame";
import { NoTeam } from "@/components/team/team-states";
import { EmptyState, ErrorState, Loading } from "@/components/ui/states";
import { useAuth } from "@/lib/auth/provider";
import { useResource } from "@/lib/data/use-resource";

export default function TeamReportsPage() {
  const { api } = useAuth();
  const { team } = useApp();
  const load = useCallback(
    (signal: AbortSignal) =>
      team ? api.teamReports(team.id, signal) : Promise.resolve({ items: [] }),
    [api, team],
  );
  const reports = useResource(
    team && team.role !== "player" ? `team-reports:${team.id}` : null,
    load,
  );
  return (
    <div className="stack">
      <div className="page-heading">
        <div>
          <span className="eyebrow">Team workspace</span>
          <h1 className="page-title">Team Reports</h1>
          <p className="page-subtitle">
            Processing summaries only. Each original PDF and its review remain
            private to its uploader.
          </p>
        </div>
      </div>
      {!team ? (
        <NoTeam />
      ) : team.role === "player" ? (
        <div className="info-box">
          Report administration is available to team coaches and admins. Your
          accepted sessions remain visible in My Sessions.
        </div>
      ) : reports.loading ? (
        <Loading />
      ) : reports.error ? (
        <ErrorState message={reports.error.message} onRetry={reports.refresh} />
      ) : !reports.data?.items.length ? (
        <EmptyState title="No team reports">
          Upload a report with this team selected, or explicitly assign an older
          processed report.
        </EmptyState>
      ) : (
        <section className="card card-pad">
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Uploaded</th>
                  <th>Status</th>
                  <th>Accepted players</th>
                </tr>
              </thead>
              <tbody>
                {reports.data.items.map((item) => (
                  <tr key={item.upload_id}>
                    <td>{new Date(item.created_at).toLocaleDateString()}</td>
                    <td>{item.status}</td>
                    <td>{item.accepted_player_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="helper mt-4">
            Open your own uploads under My Reports to review their source rows
            or private PDF.
          </p>
        </section>
      )}
    </div>
  );
}
