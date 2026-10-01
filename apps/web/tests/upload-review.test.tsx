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
  linkRow: vi.fn(),
  refresh: vi.fn(),
  api: {
    upload: vi.fn(),
    chartReviews: vi.fn(),
    linkRow: vi.fn(),
    reportFile: vi.fn(),
    proposeChart: vi.fn(),
    confirmChart: vi.fn(),
  },
}));
vi.mock("next/navigation", () => ({ useParams: () => ({ uploadId: "u1" }) }));
vi.mock("@/components/layout/app-frame", () => ({
  useApp: () => ({
    ownedPlayer: { id: "p1", display_name: "Synthetic Player" },
  }),
}));
vi.mock("@/lib/auth/provider", () => ({ useAuth: () => ({ api: mocks.api }) }));
vi.mock("@/lib/data/use-resource", () => ({
  useResource: (key: string | null) => ({
    data: key?.startsWith("upload:") ? mocks.upload : { items: [] },
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
  mocks.api.linkRow.mockReset().mockResolvedValue({
    session_id: "s1",
    player_id: "p1",
    source_athlete_row_id: "r1",
    quality_state: "accepted",
  });
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
    fireEvent.click(screen.getByRole("button", { name: /link row #3/i }));
    await waitFor(() =>
      expect(mocks.api.linkRow).toHaveBeenCalledWith(
        "u1",
        "r1",
        "p1",
        "training",
      ),
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
    expect(screen.getByText("Needs review")).toBeInTheDocument();
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
    mocks.api.linkRow.mockRejectedValue(new Error("Row not eligible"));
    render(<UploadReviewPage />);
    fireEvent.click(screen.getByRole("button", { name: "Select row" }));
    fireEvent.click(screen.getByRole("button", { name: /link row #3/i }));
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
});
