"use client";

import { CalendarDays } from "lucide-react";
import Link from "next/link";
import { useCallback, useState } from "react";
import { useApp } from "@/components/layout/app-frame";
import { SessionTable } from "@/components/sessions/session-table";
import { ErrorState, Loading } from "@/components/ui/states";
import { useAuth } from "@/lib/auth/provider";
import { useResource } from "@/lib/data/use-resource";

export default function SessionsPage() {
  const { api } = useAuth();
  const { player } = useApp();
  const [cursor, setCursor] = useState<string | undefined>();
  const load = useCallback(
    (signal: AbortSignal) => api.sessions(player.id, 20, cursor, signal),
    [api, player.id, cursor],
  );
  const sessions = useResource(
    `sessions-page:${player.id}:${cursor ?? "first"}`,
    load,
  );
  return (
    <div className="stack">
      <div className="page-heading">
        <div>
          <span className="eyebrow">Player history</span>
          <h1 className="page-title">My sessions</h1>
          <p className="page-subtitle">
            Accepted sessions linked to {player.display_name}. Source rows from
            other athletes are excluded.
          </p>
        </div>
        <Link href="/app/upload" className="btn btn-primary">
          Add report
        </Link>
      </div>
      <section className="card card-pad">
        <div className="card-head">
          <div>
            <h2 className="section-title">Session history</h2>
            <p className="section-subtitle">20 sessions per page</p>
          </div>
          <CalendarDays size={18} className="text-accent-text" />
        </div>
        {sessions.error ? (
          <ErrorState
            message={sessions.error.message}
            onRetry={sessions.refresh}
          />
        ) : sessions.loading ? (
          <Loading label="Loading sessions…" />
        ) : (
          <>
            <SessionTable sessions={sessions.data?.items ?? []} />
            {sessions.data?.next_cursor && (
              <button
                type="button"
                className="btn btn-quiet mt-4"
                onClick={() =>
                  setCursor(sessions.data?.next_cursor ?? undefined)
                }
              >
                More sessions
              </button>
            )}
          </>
        )}
      </section>
    </div>
  );
}
