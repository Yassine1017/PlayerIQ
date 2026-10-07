"use client";
import { statusText } from "@/lib/format";
import { useLocale } from "@/components/localization/locale-provider";

import Link from "next/link";
import { useCallback, useState } from "react";
import { useApp } from "@/components/layout/app-frame";
import { TeamSessionCard } from "@/components/team/team-states";
import { TeamAverageCard } from "@/components/team/team-average";
import { MyTeamComparisonPanel } from "@/components/team/my-comparison";
import { ErrorState, Loading, EmptyState } from "@/components/ui/states";
import { useAuth } from "@/lib/auth/provider";
import { useResource } from "@/lib/data/use-resource";

export default function TeamDashboardPage() {
  const { tr, ui, locale } = useLocale();

  const { api } = useAuth();
  const { team, teams, teamError, refreshTeams, selectTeam } = useApp();
  const [name, setName] = useState("");
  const [joinId, setJoinId] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState<string | Error>("");
  const load = useCallback(
    (signal: AbortSignal) =>
      team ? api.teamDashboard(team.id, signal) : Promise.resolve(null),
    [api, team],
  );
  const dashboard = useResource(
    team ? `team-dashboard:${team.id}` : null,
    load,
  );
  const loadRequests = useCallback(
    (signal: AbortSignal) =>
      team
        ? api.teamJoinRequests(team.id, signal)
        : Promise.resolve({ items: [] }),
    [api, team],
  );
  const requests = useResource(
    team?.role === "admin" ? `team-requests:${team.id}` : null,
    loadRequests,
  );
  async function create() {
    setBusy(true);
    setError("");
    try {
      const made = await api.createTeam(name.trim());
      await refreshTeams();
      selectTeam(made.id);
      setName("");
      setMessage(
        "Team created. Share its ID with invited members so they can request access.",
      );
    } catch (e) {
      setError(e instanceof Error ? e : "Could not create team");
    } finally {
      setBusy(false);
    }
  }
  async function join() {
    setBusy(true);
    setError("");
    try {
      await api.requestTeamJoin(joinId.trim());
      setMessage(
        "Request sent. A team admin must approve it before the workspace appears here.",
      );
      setJoinId("");
    } catch (e) {
      setError(e instanceof Error ? e : "Could not request access");
    } finally {
      setBusy(false);
    }
  }
  async function approve(id: string, role: "player" | "coach") {
    setBusy(true);
    setError("");
    try {
      await api.approveTeamJoin(team!.id, id, role);
      requests.refresh();
      dashboard.refresh();
    } catch (e) {
      setError(e instanceof Error ? e : "Could not approve request");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="stack">
      <div className="page-heading">
        <div>
          <span className="eyebrow">{tr("Team workspace")}</span>
          <h1 className="page-title">
            {team ? team.name : tr("Team Dashboard")}
          </h1>
          <p className="page-subtitle">
            {tr(
              "Accepted team sessions are grouped by source report. Private report review stays with the uploader.",
            )}
          </p>
        </div>
        {team && (
          <span className="status info capitalize">
            {statusText(team.role, locale)}
          </span>
        )}
      </div>
      {error && (
        <div className="error-box" role="alert">
          {ui(error)}
        </div>
      )}
      {message && (
        <div className="info-box" role="status">
          {ui(message)}
        </div>
      )}
      {teamError && (
        <ErrorState
          message={ui(teamError)}
          onRetry={() => void refreshTeams().catch(() => undefined)}
        />
      )}
      {!team && !teamError ? (
        <div className="grid-2">
          <section className="card card-pad">
            <h2 className="section-title">{tr("Create a team")}</h2>
            <p className="section-subtitle mb-4">
              {tr("Start a workspace for accepted player sessions.")}
            </p>
            <label className="field">
              {tr("Team name")}
              <input
                className="input"
                value={name}
                maxLength={160}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <button
              type="button"
              className="btn btn-primary mt-4"
              disabled={busy || name.trim().length < 2}
              onClick={() => void create()}
            >
              {tr("Create team")}
            </button>
          </section>
          <section className="card card-pad">
            <h2 className="section-title">{tr("Join a team")}</h2>
            <p className="section-subtitle mb-4">
              {tr("Ask a team admin for the team ID, then request membership.")}
            </p>
            <label className="field">
              {tr("Team ID")}
              <input
                className="input"
                value={joinId}
                onChange={(e) => setJoinId(e.target.value)}
                placeholder={tr("Team UUID")}
              />
            </label>
            <button
              type="button"
              className="btn btn-quiet mt-4"
              disabled={busy || !joinId.trim()}
              onClick={() => void join()}
            >
              {tr("Request to join")}
            </button>
          </section>
        </div>
      ) : team ? (
        <>
          {teams.length > 1 && (
            <p className="helper">
              {tr("Switch team using the selector in the top bar.")}
            </p>
          )}
          {dashboard.loading ? (
            <Loading label={tr("Loading accepted team history…")} />
          ) : dashboard.error ? (
            <ErrorState message={dashboard.error} onRetry={dashboard.refresh} />
          ) : (
            dashboard.data && (
              <>
                <div className="metric-grid">
                  <div className="card card-pad">
                    <span className="eyebrow">{tr("Latest activity")}</span>
                    <strong className="block mt-3 text-2xl">
                      {dashboard.data.latest_session?.local_date ?? "—"}
                    </strong>
                    <span className="helper">
                      {tr("Accepted team session")}
                    </span>
                  </div>
                  <div className="card card-pad">
                    <span className="eyebrow">{tr("Participants")}</span>
                    <strong className="block mt-3 text-2xl">
                      {dashboard.data.latest_session?.participant_count ?? "—"}
                    </strong>
                    <span className="helper">{tr("Latest session")}</span>
                  </div>
                  <TeamAverageCard
                    title={tr("Average distance")}
                    average={dashboard.data.latest_session?.average_distance}
                    manager={team.role !== "player"}
                    hasSession={!!dashboard.data.latest_session}
                  />
                  <TeamAverageCard
                    title={tr("Average Player Load")}
                    average={dashboard.data.latest_session?.average_player_load}
                    manager={team.role !== "player"}
                    hasSession={!!dashboard.data.latest_session}
                  />
                </div>
                <p className="helper">
                  {dashboard.data.player_count != null &&
                    tr("{count} active roster athletes", {
                      count: dashboard.data.player_count,
                    }) + " · "}
                  {tr("Latest activity averages ·")}{" "}
                  <span>
                    <bdi dir="auto">{dashboard.data.rule_version}</bdi>
                  </span>
                </p>
                <section>
                  <div className="card-head">
                    <h2 className="section-title">
                      {tr("Recent team sessions")}
                    </h2>
                    <Link href="/app/team/sessions" className="inline-link">
                      {tr("All sessions →")}
                    </Link>
                  </div>
                  {dashboard.data.recent_sessions.length ? (
                    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                      {dashboard.data.recent_sessions.map((item) => (
                        <TeamSessionCard
                          key={item.report_upload_id}
                          session={item}
                        />
                      ))}
                    </div>
                  ) : (
                    <EmptyState title={tr("No accepted team sessions yet")}>
                      {tr(
                        "Assign an existing processed report to this team or upload a new team report and import its eligible athlete rows.",
                      )}
                    </EmptyState>
                  )}
                </section>
                {dashboard.data.latest_session && (
                  <MyTeamComparisonPanel
                    key={`${team.id}:${dashboard.data.latest_session.report_upload_id}`}
                    teamId={team.id}
                    reportId={dashboard.data.latest_session.report_upload_id}
                    compact
                  />
                )}
              </>
            )
          )}
          {team.role === "admin" && (
            <section className="card card-pad">
              <div className="card-head">
                <h2 className="section-title">{tr("Membership requests")}</h2>
                <button
                  className="inline-link"
                  type="button"
                  onClick={requests.refresh}
                >
                  {tr("Refresh")}
                </button>
              </div>
              <p className="helper">
                {tr("Team ID to share privately:")}{" "}
                <code className="break-all">{team.id}</code>
              </p>
              {requests.loading ? (
                <Loading />
              ) : requests.error ? (
                <ErrorState
                  message={requests.error}
                  onRetry={requests.refresh}
                />
              ) : !requests.data?.items.length ? (
                <p className="helper mt-4">{tr("No pending requests.")}</p>
              ) : (
                <div className="grid gap-3 mt-4">
                  {requests.data.items.map((item) => (
                    <div
                      key={item.id}
                      className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-3"
                    >
                      <span className="font-semibold text-sm">
                        <bdi dir="auto">{item.display_name}</bdi>
                      </span>
                      <div className="flex gap-2">
                        <button
                          type="button"
                          className="btn btn-primary"
                          disabled={busy}
                          onClick={() => void approve(item.id, "player")}
                        >
                          {tr("Approve player")}
                        </button>
                        <button
                          type="button"
                          className="btn btn-quiet"
                          disabled={busy}
                          onClick={() => void approve(item.id, "coach")}
                        >
                          {tr("Approve coach")}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>
          )}
          <section className="card card-pad">
            <h2 className="section-title">{tr("Team access")}</h2>
            <p className="page-subtitle mt-2">
              {tr(
                "Team members see accepted activity. Only managers can inspect team players and report summaries. The uploader alone can open and review a private PDF.",
              )}
            </p>
            <div className="flex flex-wrap gap-2 mt-4">
              <Link href="/app/team/players" className="btn btn-quiet">
                {tr("Players")}
              </Link>
              {team.role !== "player" && (
                <Link href="/app/team/reports" className="btn btn-quiet">
                  {tr("Reports")}
                </Link>
              )}
            </div>
          </section>
        </>
      ) : null}
    </div>
  );
}
