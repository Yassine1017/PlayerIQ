"use client";
import { useCallback } from "react";
import { useApp } from "@/components/layout/app-frame";
import { NoTeam, TeamSessionCard } from "@/components/team/team-states";
import { EmptyState, ErrorState, Loading } from "@/components/ui/states";
import { useAuth } from "@/lib/auth/provider";
import { useResource } from "@/lib/data/use-resource";

export default function TeamSessionsPage() {
  const { api } = useAuth();
  const { team } = useApp();
  const load = useCallback(
    (signal: AbortSignal) =>
      team ? api.teamSessions(team.id, signal) : Promise.resolve({ items: [] }),
    [api, team],
  );
  const sessions = useResource(team ? `team-sessions:${team.id}` : null, load);
  return (
    <div className="stack">
      <div className="page-heading">
        <div>
          <span className="eyebrow">Team workspace</span>
          <h1 className="page-title">Team Sessions</h1>
          <p className="page-subtitle">
            One activity per source report, containing accepted and linked
            player sessions.
          </p>
        </div>
      </div>
      {!team ? (
        <NoTeam />
      ) : sessions.loading ? (
        <Loading />
      ) : sessions.error ? (
        <ErrorState
          message={sessions.error.message}
          onRetry={sessions.refresh}
        />
      ) : sessions.data?.items.length ? (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {sessions.data.items.map((item) => (
            <TeamSessionCard key={item.report_upload_id} session={item} />
          ))}
        </div>
      ) : (
        <EmptyState title="No team sessions yet">
          Accepted player sessions will appear here after a team report is
          linked.
        </EmptyState>
      )}
    </div>
  );
}
