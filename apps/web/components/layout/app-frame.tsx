"use client";

import {
  BarChart3,
  CircleUserRound,
  House,
  LogOut,
  Menu,
  UploadCloud,
  X,
  CalendarDays,
  Sparkles,
  UsersRound,
  Layers3,
  FolderOpen,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import type { Me, Player, Team } from "@/lib/api/types";
import { useAuth, authConfigured } from "@/lib/auth/provider";
import { ErrorState, Loading } from "@/components/ui/states";

interface AppContextValue {
  me: Me;
  players: Player[];
  player: Player;
  ownedPlayer: Player | null;
  teams: Team[];
  team: Team | null;
  teamError: string | null;
  refreshIdentity: () => Promise<void>;
  refreshTeams: () => Promise<void>;
  selectTeam: (id: string) => void;
}
const AppContext = createContext<AppContextValue | null>(null);
export function useApp() {
  const value = useContext(AppContext);
  if (!value) throw new Error("AppFrame is required");
  return value;
}

const personalNav = [
  { href: "/app", label: "My Dashboard", icon: House },
  { href: "/app/sessions", label: "My Sessions", icon: CalendarDays },
  { href: "/app/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/app/analyst", label: "AI Analyst", icon: Sparkles },
];
const teamNav = [
  { href: "/app/team", label: "Team Dashboard", icon: Layers3 },
  { href: "/app/team/sessions", label: "Team Sessions", icon: CalendarDays },
  { href: "/app/team/players", label: "Players", icon: UsersRound },
  { href: "/app/team/reports", label: "Team Reports", icon: FolderOpen },
];
const dataNav = [
  { href: "/app/upload", label: "My Reports", icon: UploadCloud },
];

export function AppFrame({ children }: { children: React.ReactNode }) {
  const { session, loading: authLoading, api, signOut } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [identity, setIdentity] = useState<{
    me: Me;
    players: Player[];
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [teams, setTeams] = useState<Team[]>([]);
  const [teamError, setTeamError] = useState<string | null>(null);
  const [selectedTeamId, setSelectedTeamId] = useState<string | null>(null);
  const [mobileOpen, setMobileOpen] = useState(false);
  const refreshIdentity = useCallback(async () => {
    try {
      const [me, players] = await Promise.all([api.me(), api.players()]);
      setIdentity({ me, players: players.items });
      setError(null);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Could not load your profile",
      );
    }
  }, [api]);
  const refreshTeams = useCallback(async () => {
    try {
      const result = await api.teams();
      setTeams(result.items);
      setTeamError(null);
    } catch (reason) {
      const message =
        reason instanceof Error
          ? reason.message
          : "Team workspace is unavailable";
      setTeamError(message);
      throw reason;
    }
  }, [api]);
  useEffect(() => {
    if (authLoading) return;
    if (!session) {
      router.replace("/auth/sign-in");
      return;
    }
    const controller = new AbortController();
    Promise.all([api.me(controller.signal), api.players(controller.signal)])
      .then(([me, players]) => {
        if (!controller.signal.aborted) {
          setIdentity({ me, players: players.items });
          setError(null);
        }
      })
      .catch((reason) => {
        if (!controller.signal.aborted)
          setError(
            reason instanceof Error
              ? reason.message
              : "Could not load your profile",
          );
      });
    api
      .teams(controller.signal)
      .then((foundTeams) => {
        if (!controller.signal.aborted) {
          setTeams(foundTeams.items);
          setTeamError(null);
        }
      })
      .catch((reason) => {
        if (!controller.signal.aborted)
          setTeamError(
            reason instanceof Error
              ? reason.message
              : "Team workspace is unavailable",
          );
      });
    return () => controller.abort();
  }, [authLoading, session, router, api]);
  if (!authConfigured)
    return (
      <div className="min-h-screen grid place-items-center p-5">
        <ErrorState message="Public Supabase configuration is missing. Add NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY to apps/web/.env.local." />
      </div>
    );
  if (authLoading || !session || (!identity && !error))
    return (
      <div className="min-h-screen grid place-items-center p-5">
        <Loading label="Opening your workspace…" />
      </div>
    );
  if (error && !identity)
    return (
      <div className="min-h-screen grid place-items-center p-5">
        <ErrorState message={error} onRetry={() => void refreshIdentity()} />
      </div>
    );
  if (!identity) return null;
  const ownedPlayer =
    identity.players.find(
      (item) => item.owner_user_id === identity.me.user_id,
    ) ?? null;
  if (!identity.me.profile || !ownedPlayer)
    return (
      <Onboarding
        me={identity.me}
        hasPlayer={Boolean(ownedPlayer)}
        onDone={refreshIdentity}
      />
    );
  const player = ownedPlayer;
  const team =
    teams.find((item) => item.id === selectedTeamId) ?? teams[0] ?? null;
  const selected = [...personalNav, ...teamNav, ...dataNav]
    .sort((a, b) => b.href.length - a.href.length)
    .find(
      (item) =>
        pathname === item.href ||
        (item.href !== "/app" && pathname.startsWith(`${item.href}/`)),
    );
  const title = pathname.startsWith("/app/uploads/")
    ? "Report Review"
    : pathname.startsWith("/app/profile")
      ? "Profile & Settings"
      : (selected?.label ?? "PlayerIQ");
  const initials = (identity.me.profile.display_name || player.display_name)
    .split(/\s+/)
    .slice(0, 2)
    .map((s) => s[0])
    .join("")
    .toUpperCase();
  return (
    <AppContext.Provider
      value={{
        me: identity.me,
        players: identity.players,
        player,
        ownedPlayer,
        teams,
        team,
        teamError,
        refreshIdentity,
        refreshTeams,
        selectTeam: setSelectedTeamId,
      }}
    >
      <div className="app-shell">
        {mobileOpen && (
          <button
            type="button"
            className="fixed inset-0 z-20 bg-slate-950/40"
            onClick={() => setMobileOpen(false)}
            aria-label="Close navigation"
          />
        )}
        <aside
          className={`sidebar ${mobileOpen ? "open" : ""}`}
          aria-label="Primary navigation"
        >
          <div className="flex items-start justify-between px-3">
            <Link href="/app" className="brand">
              Player<span>IQ</span>
              <small className="brand-tag">Performance intelligence</small>
            </Link>
            <button
              type="button"
              className="mobile-menu text-white"
              onClick={() => setMobileOpen(false)}
              aria-label="Close menu"
            >
              <X size={20} />
            </button>
          </div>
          <div className="side-section">Personal</div>
          <nav aria-label="Personal">
            {personalNav.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setMobileOpen(false)}
                className={`nav-link ${pathname === item.href || (item.href !== "/app" && pathname.startsWith(`${item.href}/`)) ? "active" : ""}`}
                aria-current={pathname === item.href ? "page" : undefined}
              >
                <item.icon size={17} />
                {item.label}
              </Link>
            ))}
          </nav>
          <div className="side-section">Team</div>
          <nav aria-label="Team">
            {teamNav.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setMobileOpen(false)}
                className={`nav-link ${pathname === item.href || (item.href !== "/app/team" && pathname.startsWith(`${item.href}/`)) ? "active" : ""}`}
              >
                <item.icon size={17} />
                {item.label}
              </Link>
            ))}
          </nav>
          <div className="side-section">Data</div>
          <nav aria-label="Data">
            {dataNav.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setMobileOpen(false)}
                className={`nav-link ${pathname === item.href || pathname.startsWith("/app/uploads/") ? "active" : ""}`}
              >
                <item.icon size={17} />
                {item.label}
              </Link>
            ))}
          </nav>
          <div className="side-foot">
            <div className="side-user">
              <span className="avatar">{initials}</span>
              <span>
                <strong className="block text-white">
                  {identity.me.profile.display_name}
                </strong>
                <span className="text-slate-400">PlayerIQ account</span>
              </span>
            </div>
            <Link
              href="/app/profile"
              className={`nav-link ${pathname === "/app/profile" ? "active" : ""}`}
            >
              <CircleUserRound size={17} /> Profile & Settings
            </Link>
            <button
              type="button"
              className="nav-link"
              onClick={() => void signOut()}
            >
              <LogOut size={17} /> Sign Out
            </button>
          </div>
        </aside>
        <div className="workspace">
          <header className="topbar">
            <div className="flex items-center gap-3">
              <button
                type="button"
                className="mobile-menu btn btn-quiet !p-2"
                onClick={() => setMobileOpen(true)}
                aria-label="Open navigation"
              >
                <Menu size={18} />
              </button>
              <span className="topbar-title">
                Workspace <span className="mx-2 text-slate-300">/</span>{" "}
                <strong className="text-slate-800">{title}</strong>
              </span>
            </div>
            <div className="topbar-right">
              {pathname.startsWith("/app/team") && teams.length > 1 ? (
                <label className="relative">
                  <span className="sr-only">Selected team</span>
                  <select
                    className="topbar-player pr-7"
                    value={team?.id ?? ""}
                    onChange={(event) => setSelectedTeamId(event.target.value)}
                  >
                    {teams.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                  </select>
                </label>
              ) : (
                <span className="topbar-player">
                  {pathname.startsWith("/app/team")
                    ? (team?.name ?? "Team workspace")
                    : player.display_name}
                </span>
              )}
              <span className="avatar">{initials}</span>
            </div>
          </header>
          <main className="content">
            {error && (
              <div className="error-box mb-4">
                {error}{" "}
                <button
                  type="button"
                  onClick={() => void refreshIdentity()}
                  className="underline"
                >
                  Retry
                </button>
              </div>
            )}
            {children}
          </main>
        </div>
      </div>
    </AppContext.Provider>
  );
}

function Onboarding({
  me,
  hasPlayer,
  onDone,
}: {
  me: Me;
  hasPlayer: boolean;
  onDone: () => Promise<void>;
}) {
  const { api } = useAuth();
  const [name, setName] = useState(me.profile?.display_name ?? "");
  const [playerName, setPlayerName] = useState("");
  const [timezone, setTimezone] = useState(
    Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (!me.profile)
        await api.updateMe({ display_name: name.trim(), timezone });
      if (!hasPlayer) await api.createPlayer(playerName.trim());
      await onDone();
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Could not save setup",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="min-h-screen grid place-items-center p-5">
      <div className="card card-pad w-full max-w-lg">
        <span className="eyebrow">Welcome to PlayerIQ</span>
        <h1 className="page-title mt-2">Set up your workspace</h1>
        <p className="page-subtitle mb-6">
          Create your profile and choose the player you’ll track. Reports are
          linked only when you explicitly select an athlete row.
        </p>
        <form onSubmit={(event) => void submit(event)} className="grid gap-4">
          {!me.profile && (
            <>
              <label className="field">
                Your display name
                <input
                  className="input"
                  required
                  maxLength={160}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </label>
              <label className="field">
                Time zone
                <input
                  className="input"
                  required
                  value={timezone}
                  onChange={(e) => setTimezone(e.target.value)}
                />
              </label>
            </>
          )}
          {!hasPlayer && (
            <label className="field">
              Player profile name
              <input
                className="input"
                required
                maxLength={160}
                value={playerName}
                onChange={(e) => setPlayerName(e.target.value)}
                placeholder="Name used in PlayerIQ"
              />
            </label>
          )}
          {error && (
            <div className="error-box" role="alert">
              {error}
            </div>
          )}
          <button type="submit" disabled={busy} className="btn btn-primary">
            {busy ? "Saving…" : "Open dashboard"}
          </button>
        </form>
      </div>
    </div>
  );
}
