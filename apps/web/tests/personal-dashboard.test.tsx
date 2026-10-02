import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Dashboard from "@/app/app/page";
import { fact, playerSession } from "./fixtures";

const mocks = vi.hoisted(() => ({
  resources: {} as Record<string, unknown>,
}));
vi.mock("@/components/layout/app-frame", () => ({
  useApp: () => ({
    player: { id: "p1", display_name: "Alex Morgan" },
    team: { name: "Synthetic FC" },
  }),
}));
vi.mock("@/lib/auth/provider", () => ({
  useAuth: () => ({ api: {} }),
}));
vi.mock("@/lib/data/use-resource", () => ({
  useResource: (key: string) => ({
    data: mocks.resources[key] ?? null,
    loading: false,
    error: null,
    refresh: vi.fn(),
  }),
}));
vi.mock("@/components/analytics/trend-chart", () => ({
  TrendChart: () => <div>Trend visualization</div>,
}));

beforeEach(() => {
  mocks.resources = {
    "dashboard-identities:p1": { items: [] },
    "overview:p1": { facts: [] },
    "sessions:p1": { items: [] },
  };
});
afterEach(cleanup);

describe("personal dashboard", () => {
  it("shows identity and accepted-session first-use guidance without fabricated zeros", () => {
    render(<Dashboard />);
    expect(screen.getByText("Connect your GPS identity")).toBeInTheDocument();
    expect(screen.getByText("No accepted sessions yet")).toBeInTheDocument();
    expect(screen.getByText(/No accepted session yet/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open analyst/i })).toHaveAttribute(
      "href",
      "/app/analyst",
    );
    expect(screen.queryByText("0 km/h")).not.toBeInTheDocument();
  });

  it("shows accepted history and team context from backend data", () => {
    mocks.resources["dashboard-identities:p1"] = {
      items: [{ id: "identity-1", status: "connected" }],
    };
    mocks.resources["sessions:p1"] = { items: [playerSession] };
    mocks.resources["overview:p1"] = { facts: [fact] };
    render(<Dashboard />);
    expect(screen.getByText(/Latest accepted session:/)).toHaveTextContent(
      "Synthetic FC",
    );
    expect(screen.getAllByText("8,400 m").length).toBeGreaterThan(0);
    expect(
      screen.queryByText("Connect your GPS identity"),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /view all/i })).toHaveAttribute(
      "href",
      "/app/sessions",
    );
  });
});
