import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import TeamDashboardPage from "@/app/app/team/page";
import TeamSessionsPage from "@/app/app/team/sessions/page";
import TeamSessionDetailPage from "@/app/app/team/sessions/[reportId]/page";
import TeamPlayersPage from "@/app/app/team/players/page";
import TeamReportsPage from "@/app/app/team/reports/page";
import { TeamAverageCard } from "@/components/team/team-average";

const mocks = vi.hoisted(() => ({
  team: null as null | {
    id: string;
    name: string;
    role: "admin" | "player";
    player_id: string | null;
    created_at: string;
  },
  resources: {} as Record<string, unknown>,
  api: {
    teamDashboard: vi.fn(),
    teamSessions: vi.fn(),
    teamSession: vi.fn(),
    teamPlayers: vi.fn(),
    teamReports: vi.fn(),
    teamJoinRequests: vi.fn(),
  },
  refreshTeams: vi.fn(),
  selectTeam: vi.fn(),
}));
vi.mock("next/navigation", () => ({
  useParams: () => ({ reportId: "report-1" }),
}));
vi.mock("@/components/layout/app-frame", () => ({
  useApp: () => ({
    team: mocks.team,
    teams: mocks.team ? [mocks.team] : [],
    teamError: null,
    refreshTeams: mocks.refreshTeams,
    selectTeam: mocks.selectTeam,
  }),
}));
vi.mock("@/lib/auth/provider", () => ({ useAuth: () => ({ api: mocks.api }) }));
vi.mock("@/lib/data/use-resource", () => ({
  useResource: (key: string | null) => ({
    data: key ? (mocks.resources[key] ?? null) : null,
    loading: false,
    error: null,
    refresh: vi.fn(),
  }),
}));

const activity = {
  report_upload_id: "report-1",
  local_date: "2026-02-01",
  participant_count: 2,
  total_distance_m: "6200",
  session_type: "training",
};
beforeEach(() => {
  mocks.team = {
    id: "team-1",
    name: "Synthetic FC",
    role: "admin",
    player_id: "p1",
    created_at: "2026-01-01",
  };
  mocks.resources = {};
});
afterEach(cleanup);

const mean = {
  metric_key: "total_distance_m",
  status: "ok" as const,
  value: "3100",
  display_value: "3100",
  unit: "m",
  sample_size: 2,
  session_ids: ["s1", "s2"],
  source_observation_ids: ["o1", "o2"],
  comparison_scope: "same_report" as const,
  rule_version: "analytics_v1" as const,
};

describe("team workspace views", () => {
  it("shows create and join paths when no team exists", () => {
    mocks.team = null;
    render(<TeamDashboardPage />);
    expect(
      screen.getByRole("heading", { name: "Create a team" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Join a team" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("6,200 m combined distance"),
    ).not.toBeInTheDocument();
  });
  it("shows accepted activity and rule version on the team dashboard", () => {
    mocks.resources["team-dashboard:team-1"] = {
      team: mocks.team,
      latest_session: {
        ...activity,
        average_distance: mean,
        average_player_load: {
          ...mean,
          metric_key: "player_load_reported",
          value: "410.5",
          unit: "source units",
        },
      },
      recent_sessions: [{ ...activity, average_distance: mean }],
      player_count: 2,
      rule_version: "analytics_v1",
    };
    mocks.resources["team-requests:team-1"] = { items: [] };
    render(<TeamDashboardPage />);
    expect(
      screen.getByRole("heading", { name: "Synthetic FC" }),
    ).toBeInTheDocument();
    expect(screen.getByText("analytics_v1")).toBeInTheDocument();
    expect(screen.getByText("Average distance")).toBeInTheDocument();
    expect(screen.getByText("Average Player Load")).toBeInTheDocument();
    expect(screen.getByText("3,100 m")).toBeInTheDocument();
    expect(screen.getByText("410.5")).toBeInTheDocument();
    expect(
      screen.getAllByText(/2 accepted players with this metric/),
    ).toHaveLength(2);
    expect(screen.queryByText("ATHLETE1")).not.toBeInTheDocument();
  });
  it("groups team sessions by report and offers a drilldown", () => {
    mocks.resources["team-sessions:team-1"] = { items: [activity] };
    render(<TeamSessionsPage />);
    expect(screen.getByRole("link", { name: /View/ })).toHaveAttribute(
      "href",
      "/app/team/sessions/report-1",
    );
    expect(screen.getByText("6,200 m combined distance")).toBeInTheDocument();
  });
  it("renders only participant data returned by the authorized detail API", () => {
    mocks.team = { ...mocks.team!, role: "player", player_id: "p1" };
    mocks.resources["team-session:team-1:report-1"] = {
      summary: activity,
      participants: [
        {
          player_id: "p1",
          display_name: "Alex Morgan",
          session_id: "session-1",
          metrics: [
            { metric_key: "maximum_velocity_kmh", value: "30.2", unit: "km/h" },
          ],
        },
      ],
    };
    render(<TeamSessionDetailPage />);
    expect(screen.getByText("Alex Morgan")).toBeInTheDocument();
    expect(screen.getByText("30.2 km/h")).toBeInTheDocument();
    expect(screen.queryByText("Jordan Lee")).not.toBeInTheDocument();
  });
  it("limits a player directory to the API-authorized entries", () => {
    mocks.team = { ...mocks.team!, role: "player", player_id: "p1" };
    mocks.resources["team-players:team-1"] = {
      items: [
        {
          id: "p1",
          display_name: "Alex Morgan",
          latest_session_date: "2026-02-01",
          latest_metrics: [],
        },
      ],
      limited_to_self: true,
    };
    render(<TeamPlayersPage />);
    expect(screen.getByText("Alex Morgan")).toBeInTheDocument();
    expect(screen.getByText(/your own performance/i)).toBeInTheDocument();
  });
  it("does not render team report administration for player role", () => {
    mocks.team = { ...mocks.team!, role: "player", player_id: "p1" };
    render(<TeamReportsPage />);
    expect(
      screen.getByText(/available to team coaches and admins/i),
    ).toBeInTheDocument();
  });
  it("keeps an unclaimed nonparticipant visible without invented activity", () => {
    mocks.resources["team-players:team-1"] = {
      items: [
        {
          id: "unclaimed",
          display_name: "Synthetic Nonparticipant",
          account_state: "unclaimed",
          participation_state: "no_accepted_activity",
          latest_session_date: null,
          latest_metrics: [],
        },
      ],
      limited_to_self: false,
    };
    render(<TeamPlayersPage />);
    expect(screen.getByText("Synthetic Nonparticipant")).toBeInTheDocument();
    expect(screen.getByText("Unclaimed athlete")).toBeInTheDocument();
    expect(screen.getByText("No accepted activity")).toBeInTheDocument();
    expect(screen.queryByText("0 m")).not.toBeInTheDocument();
  });
  it("keeps missing, zero and incompatible mean states distinct", () => {
    const view = render(
      <TeamAverageCard
        title="Average distance"
        average={{
          ...mean,
          status: "missing_metric",
          value: null,
          sample_size: 0,
        }}
        manager
        hasSession
      />,
    );
    expect(screen.getByText("No accepted metric values")).toBeInTheDocument();
    expect(screen.queryByText("0 m")).not.toBeInTheDocument();
    view.rerender(
      <TeamAverageCard
        title="Average distance"
        average={{ ...mean, value: "0" }}
        manager
        hasSession
      />,
    );
    expect(screen.getByText("0 m")).toBeInTheDocument();
    view.rerender(
      <TeamAverageCard
        title="Average distance"
        average={{ ...mean, status: "not_comparable", value: null }}
        manager
        hasSession
      />,
    );
    expect(screen.getByText("Source definitions differ")).toBeInTheDocument();
    view.rerender(
      <TeamAverageCard
        title="Average distance"
        average={null}
        manager={false}
        hasSession
      />,
    );
    expect(screen.getByText("Private to team managers")).toBeInTheDocument();
  });
  it("offers report import for an empty roster", () => {
    mocks.resources["team-players:team-1"] = {
      items: [],
      limited_to_self: false,
    };
    render(<TeamPlayersPage />);
    expect(
      screen.getByText(/Import a GPS report into this team/),
    ).toBeInTheDocument();
  });
});
