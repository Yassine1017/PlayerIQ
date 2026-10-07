"use client";
import { statusText, dateLabel } from "@/lib/format";
import { useLocale } from "@/components/localization/locale-provider";
import { useCallback } from "react";
import { useApp } from "@/components/layout/app-frame";
import { NoTeam } from "@/components/team/team-states";
import { EmptyState, ErrorState, Loading } from "@/components/ui/states";
import { useAuth } from "@/lib/auth/provider";
import { useResource } from "@/lib/data/use-resource";

export default function TeamReportsPage() {
  const { tr, locale } = useLocale();

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
          <span className="eyebrow">{tr("Team workspace")}</span>
          <h1 className="page-title">{tr("Team Reports")}</h1>
          <p className="page-subtitle">
            {tr(
              "Processing summaries only. Each original PDF and its review remain private to its uploader.",
            )}
          </p>
        </div>
      </div>
      {!team ? (
        <NoTeam />
      ) : team.role === "player" ? (
        <div className="info-box">
          {tr(
            "Report administration is available to team coaches and admins. Your accepted sessions remain visible in My Sessions.",
          )}
        </div>
      ) : reports.loading ? (
        <Loading />
      ) : reports.error ? (
        <ErrorState message={reports.error} onRetry={reports.refresh} />
      ) : !reports.data?.items.length ? (
        <EmptyState title={tr("No team reports")}>
          {tr(
            "Upload a report with this team selected, or explicitly assign an older processed report.",
          )}
        </EmptyState>
      ) : (
        <section className="card card-pad">
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>{tr("Uploaded")}</th>
                  <th>{tr("Status")}</th>
                  <th>{tr("Accepted players")}</th>
                </tr>
              </thead>
              <tbody>
                {reports.data.items.map((item) => (
                  <tr key={item.upload_id}>
                    <td>{dateLabel(item.created_at, locale)}</td>
                    <td>{statusText(item.status, locale)}</td>
                    <td>{item.accepted_player_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="helper mt-4">
            {tr(
              "Open your own uploads under My Reports to review their source rows or private PDF.",
            )}
          </p>
        </section>
      )}
    </div>
  );
}
