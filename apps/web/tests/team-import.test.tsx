import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { TeamImportPanel } from "@/components/uploads/team-import-panel";
import type { TeamImport, TeamPlayer } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  data: null as TeamImport | null,
  error: null as Error | null,
  refresh: vi.fn(),
  api: {
    teamImport: vi.fn(),
    requestTeamImport: vi.fn(),
    resolveTeamImport: vi.fn(),
  },
}));
vi.mock("@/lib/auth/provider", () => ({ useAuth: () => ({ api: mocks.api }) }));
vi.mock("@/lib/data/use-resource", () => ({
  useResource: () => ({
    data: mocks.data,
    loading: false,
    error: mocks.error,
    refresh: mocks.refresh,
  }),
}));
afterEach(cleanup);
beforeEach(() => {
  mocks.data = null;
  mocks.error = null;
  vi.clearAllMocks();
  mocks.api.requestTeamImport.mockResolvedValue({});
  mocks.api.resolveTeamImport.mockResolvedValue({});
});
const player: TeamPlayer = {
  id: "p1",
  display_name: "Synthetic Athlete",
  account_state: "unclaimed",
  participation_state: "accepted_history",
  latest_session_date: "2026-01-01",
  latest_metrics: [],
};
const result: TeamImport = {
  upload_id: "u1",
  team_id: "t1",
  status: "needs_review",
  session_type: "training",
  attempts: 1,
  error_code: null,
  created_at: "2026-01-01",
  finished_at: "2026-01-01",
  counts: {
    total: 18,
    created_players: 18,
    accepted_session: 15,
    accepted_sessions: 15,
    no_activity: 2,
  },
  rows: [
    {
      row_id: "r1",
      row_ordinal: 1,
      source_name: "SYNTHETIC ONE",
      player_id: "p1",
      session_id: null,
      association_method: "team_report_import",
      outcome: "no_activity",
      reason_code: "no_recorded_activity",
      created_player: true,
      created_session: false,
      resolved_at: null,
    },
  ],
};
function mount() {
  return render(
    <TeamImportPanel
      uploadId="u1"
      teamId="t1"
      players={[player]}
      onChanged={vi.fn()}
    />,
  );
}

it("requires explicit report-level sharing and keeps the type unknown by default", async () => {
  mount();
  expect(
    screen.getByRole("button", { name: "Import all athletes" }),
  ).toBeDisabled();
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(screen.getByRole("button", { name: "Import all athletes" }));
  await waitFor(() =>
    expect(mocks.api.requestTeamImport).toHaveBeenCalledWith(
      "u1",
      "t1",
      "unknown",
    ),
  );
});
it("shows backend counts and distinguishes roster-only activity", () => {
  mocks.data = result;
  mount();
  expect(
    screen.getByText(/18 athletes · 18 new profiles · 15 accepted sessions/),
  ).toBeInTheDocument();
  expect(
    screen.getByText("No recorded activity · roster only"),
  ).toBeInTheDocument();
  expect(screen.getByText("Imported unclaimed athlete")).toBeInTheDocument();
});
it("requires deliberate association confirmation and sends the exact source row label", async () => {
  mocks.data = result;
  mount();
  fireEvent.click(screen.getByRole("button", { name: "Review association" }));
  expect(
    screen.getByRole("button", { name: "Confirm athlete association" }),
  ).toBeDisabled();
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(
    screen.getByRole("button", { name: "Confirm athlete association" }),
  );
  await waitFor(() =>
    expect(mocks.api.resolveTeamImport).toHaveBeenCalledWith(
      "u1",
      "r1",
      "p1",
      "SYNTHETIC ONE",
    ),
  );
});
it("renders queued progress and failed retry with the original session type", async () => {
  mocks.data = { ...result, status: "queued", rows: [] };
  const view = mount();
  expect(screen.getByText(/Roster import queued/)).toBeInTheDocument();
  mocks.data = { ...result, status: "failed", rows: [] };
  view.rerender(
    <TeamImportPanel
      uploadId="u1"
      teamId="t1"
      players={[]}
      onChanged={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Retry import" }));
  await waitFor(() =>
    expect(mocks.api.requestTeamImport).toHaveBeenCalledWith(
      "u1",
      "t1",
      "training",
    ),
  );
});
it("shows safe API and mutation errors", async () => {
  mocks.api.requestTeamImport.mockRejectedValue(
    new Error("Team access changed"),
  );
  mount();
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(screen.getByRole("button", { name: "Import all athletes" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Something went wrong. Please try again.",
  );
});
