import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import UploadReviewPage from "@/app/app/uploads/[uploadId]/page";
import type { UploadStatus } from "@/lib/api/types";
import { row } from "./fixtures";

const mocks = vi.hoisted(() => ({
  upload: null as UploadStatus | null,
  teams: [] as { id: string; name: string; role: string }[],
  teamPlayers: [] as { id: string; display_name: string }[],
  linkRow: vi.fn(),
  refresh: vi.fn(),
  api: {
    upload: vi.fn(),
    chartReviews: vi.fn(),
    linkRow: vi.fn(),
    claimSelf: vi.fn(),
    confirmTeamPlayer: vi.fn(),
    teamPlayers: vi.fn(),
    reportFile: vi.fn(),
    proposeChart: vi.fn(),
    confirmChart: vi.fn(),
  },
}));
vi.mock("next/navigation", () => ({ useParams: () => ({ uploadId: "u1" }) }));
vi.mock("@/components/layout/app-frame", () => ({
  useApp: () => ({
    ownedPlayer: { id: "p1", display_name: "Synthetic Player" },
    teams: mocks.teams,
  }),
}));
vi.mock("@/lib/auth/provider", () => ({ useAuth: () => ({ api: mocks.api }) }));
vi.mock("@/lib/data/use-resource", () => ({
  useResource: (key: string | null) => ({
    data: key?.startsWith("upload:")
      ? mocks.upload
      : key?.startsWith("upload-team-players:")
        ? { items: mocks.teamPlayers }
        : { items: [] },
    error: null,
    loading: false,
    refresh: mocks.refresh,
  }),
}));
const base: UploadStatus = {
  upload_id: "u1",
  status: "awaiting_link",
  error_code: null,
  activity: {
    source_title: "Synthetic training report",
    source_team_name: null,
    source_venue_name: null,
    reported_local_datetime: "2026-02-01T17:00:00",
    timezone: "UTC",
    activity_total_time_s: 3600,
  },
  findings: [],
  candidate_rows: [row],
};
beforeEach(() => {
  mocks.upload = base;
  mocks.teams = [];
  mocks.teamPlayers = [];
  mocks.api.linkRow.mockReset().mockResolvedValue({
    session_id: "s1",
    player_id: "p1",
    source_athlete_row_id: "r1",
    quality_state: "accepted",
  });
  mocks.api.claimSelf
    .mockReset()
    .mockResolvedValue({ session_id: "s1", identity: { id: "i1" } });
  mocks.api.confirmTeamPlayer
    .mockReset()
    .mockResolvedValue({ session_id: "s2", identity: { id: "i2" } });
  mocks.refresh.mockClear();
});
afterEach(cleanup);
describe("uploader review flow", () => {
  it("requires deliberate athlete selection and explicit linking", async () => {
    render(<UploadReviewPage />);
    expect(screen.getByText("Synthetic Athlete C")).toBeInTheDocument();
    expect(mocks.api.linkRow).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Select row" }));
    expect(screen.getByText(/selected athlete row #3/i)).toBeInTheDocument();
    const button = screen.getByRole("button", { name: /this is me/i });
    expect(button).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(button);
    await waitFor(() =>
      expect(mocks.api.claimSelf).toHaveBeenCalledWith("u1", {
        source_athlete_row_id: "r1",
        player_id: "p1",
        confirmed_source_label: "Synthetic Athlete C",
        session_type: "training",
      }),
    );
    expect(await screen.findByText("Session linked")).toBeInTheDocument();
  });
  it("distinguishes zero activity and needs review from linkable rows", () => {
    mocks.upload = {
      ...base,
      candidate_rows: [
        {
          ...row,
          id: "r-zero",
          row_ordinal: 4,
          source_name: "Synthetic Zero",
          quality_state: "zero_recorded",
        },
        {
          ...row,
          id: "r-held",
          row_ordinal: 5,
          source_name: "Synthetic Review",
          quality_state: "needs_review",
        },
      ],
    };
    render(<UploadReviewPage />);
    expect(screen.getByText("Zero activity recorded")).toBeInTheDocument();
    expect(screen.getAllByText("Needs review").length).toBeGreaterThan(0);
    expect(
      screen.queryByRole("button", { name: "Select row" }),
    ).not.toBeInTheDocument();
    expect(mocks.api.linkRow).not.toHaveBeenCalled();
  });
  it("shows processing and rejected states without a link action", () => {
    mocks.upload = { ...base, status: "queued", candidate_rows: [] };
    const view = render(<UploadReviewPage />);
    expect(
      screen.getByText(/checking again every 5 seconds/i),
    ).toBeInTheDocument();
    view.unmount();
    mocks.upload = {
      ...base,
      status: "rejected",
      error_code: "unsupported_layout",
      candidate_rows: [],
    };
    render(<UploadReviewPage />);
    expect(screen.getByText(/unsupported_layout/)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /link row/i }),
    ).not.toBeInTheDocument();
  });
  it("surfaces failed linking without a success state", async () => {
    mocks.api.claimSelf.mockRejectedValue(new Error("Row not eligible"));
    render(<UploadReviewPage />);
    fireEvent.click(screen.getByRole("button", { name: "Select row" }));
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: /this is me/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Row not eligible",
    );
    expect(screen.queryByText("Session linked")).not.toBeInTheDocument();
  });
  it("shows automatic, review, and unavailable chart states", () => {
    mocks.upload = {
      ...base,
      candidate_rows: [
        {
          ...row,
          metrics: [
            ...row.metrics,
            {
              source_label: "Maximum Velocity",
              raw_value: "29.75",
              raw_unit: "km/h",
              parsed_value: "29.75",
              quality_state: "accepted",
              source_locator: "p2 chart method:pdf_position",
            },
            {
              source_label: "Player Load",
              raw_value: "420",
              raw_unit: null,
              parsed_value: "420",
              quality_state: "needs_review",
              source_locator: "p2 chart method:ocr confidence:0.91",
            },
          ],
        },
        {
          ...row,
          id: "r-missing",
          row_ordinal: 4,
          source_name: "Synthetic Other",
        },
      ],
    };
    render(<UploadReviewPage />);
    expect(screen.getByText("29.75")).toBeInTheDocument();
    expect(screen.getByText("420")).toBeInTheDocument();
    expect(screen.getByText("Automatically extracted")).toBeInTheDocument();
    expect(screen.getByText("Needs review")).toBeInTheDocument();
    expect(screen.getAllByText("Unavailable")).toHaveLength(2);
  });
  it("requires confirmation even when a future row is recognized", async () => {
    mocks.upload = {
      ...base,
      candidate_rows: [
        {
          ...row,
          recognition_status: "recognized",
          recognized_player_id: "p1",
          source_identity_id: "identity-1",
        },
      ],
    };
    render(<UploadReviewPage />);
    expect(screen.getByText("Recognized · confirm")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Select row" }));
    const link = screen.getByRole("button", {
      name: /confirm recognized link/i,
    });
    expect(link).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(link);
    await waitFor(() =>
      expect(mocks.api.linkRow).toHaveBeenCalledWith(
        "u1",
        "r1",
        "p1",
        "training",
        "identity-1",
      ),
    );
    expect(mocks.api.claimSelf).not.toHaveBeenCalled();
  });
  it("lets a team uploader explicitly confirm a teammate identity", async () => {
    mocks.upload = { ...base, team_id: "t1" };
    mocks.teams = [{ id: "t1", name: "Synthetic FC", role: "admin" }];
    mocks.teamPlayers = [
      { id: "p1", display_name: "Synthetic Player" },
      { id: "p2", display_name: "Jordan Lee" },
    ];
    render(<UploadReviewPage />);
    fireEvent.click(screen.getByRole("button", { name: "Select row" }));
    fireEvent.change(screen.getByLabelText("Link to player"), {
      target: { value: "p2" },
    });
    expect(
      screen.getByText("Confirm this team player's row"),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(
      screen.getByRole("button", { name: /confirm team player link/i }),
    );
    await waitFor(() =>
      expect(mocks.api.confirmTeamPlayer).toHaveBeenCalledWith("u1", {
        source_athlete_row_id: "r1",
        player_id: "p2",
        confirmed_source_label: "Synthetic Athlete C",
        session_type: "training",
      }),
    );
  });
  it("defaults a recognized team row to its confirmed player", () => {
    mocks.upload = {
      ...base,
      team_id: "t1",
      candidate_rows: [
        {
          ...row,
          recognition_status: "recognized",
          recognized_player_id: "p2",
          source_identity_id: "identity-2",
        },
      ],
    };
    mocks.teams = [{ id: "t1", name: "Synthetic FC", role: "admin" }];
    mocks.teamPlayers = [
      { id: "p1", display_name: "Synthetic Player" },
      { id: "p2", display_name: "Jordan Lee" },
    ];
    render(<UploadReviewPage />);
    fireEvent.click(screen.getByRole("button", { name: "Select row" }));
    expect(screen.getByLabelText("Link to player")).toHaveValue("p2");
    expect(screen.getByText("Recognized source identity")).toBeInTheDocument();
  });
});
