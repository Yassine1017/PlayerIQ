import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { IdentityOnboarding } from "@/components/identity/identity-onboarding";
import ConnectIdentityPage from "@/app/app/connect/page";
import type { IdentityReports } from "@/lib/data/use-identity-reports";
import { row } from "./fixtures";

const mocks = vi.hoisted(() => ({
  data: null as IdentityReports | null,
  replace: vi.fn(),
  refresh: vi.fn(),
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mocks.replace }),
}));
vi.mock("@/components/layout/app-frame", () => ({
  useApp: () => ({ player: { id: "p1" } }),
}));
vi.mock("@/lib/auth/provider", () => ({ useAuth: () => ({ api: {} }) }));
vi.mock("@/lib/data/use-identity-reports", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/data/use-identity-reports")>()),
  useIdentityReports: () => ({
    data: mocks.data,
    loading: false,
    error: null,
    refresh: mocks.refresh,
    loadMore: vi.fn(),
    atLimit: false,
  }),
}));
function choice(id: string) {
  return {
    upload: {
      upload_id: id,
      original_filename: "synthetic.pdf",
      status: "awaiting_link",
      created_at: "2026-01-01",
      processed_at: "2026-01-01",
      athlete_row_count: 1,
      error_code: null,
    },
    report: {
      upload_id: id,
      status: "awaiting_link",
      error_code: null,
      findings: [],
      candidate_rows: [row],
      activity: {
        source_title: `Synthetic report ${id}`,
        source_team_name: null,
        source_venue_name: null,
        reported_local_datetime: "2026-02-01T17:00:00",
        timezone: null,
        activity_total_time_s: null,
      },
    },
  };
}
beforeEach(() => {
  mocks.data = { uploads: [], eligible: [], nextCursor: null };
  mocks.replace.mockReset();
});
afterEach(cleanup);
describe("guided identity entry", () => {
  it("offers upload and marks every step pending when there is no report", () => {
    render(<IdentityOnboarding />);
    expect(
      screen.getByRole("link", { name: /upload a GPS report/i }),
    ).toHaveAttribute("href", "/app/upload");
    expect(screen.getAllByText(/— pending/)).toHaveLength(3);
    expect(screen.queryByText(/— complete/)).not.toBeInTheDocument();
  });
  it("takes a single eligible report directly to its visible identity section", () => {
    const report = choice("u1");
    mocks.data = {
      uploads: [report.upload],
      eligible: [report],
      nextCursor: null,
    };
    render(<IdentityOnboarding />);
    expect(
      screen.getByRole("link", { name: /choose my player identity/i }),
    ).toHaveAttribute("href", "/app/uploads/u1#player-identity");
    expect(screen.getAllByText(/— complete/)).toHaveLength(1);
  });
  it("opens the report picker when several eligible reports exist", () => {
    mocks.data = {
      uploads: [choice("u1").upload, choice("u2").upload],
      eligible: [choice("u1"), choice("u2")],
      nextCursor: null,
    };
    render(<IdentityOnboarding />);
    expect(
      screen.getByRole("link", { name: /choose my player identity/i }),
    ).toHaveAttribute("href", "/app/connect");
  });
  it("shows the actual queued state without completing athlete selection", () => {
    mocks.data = {
      uploads: [{ ...choice("u1").upload, status: "queued" }],
      eligible: [],
      nextCursor: null,
    };
    render(<IdentityOnboarding />);
    expect(screen.getByRole("status")).toHaveTextContent(/queued/i);
    expect(screen.getAllByText(/— pending/)).toHaveLength(2);
    expect(
      screen.getByRole("link", { name: /upload a GPS report/i }),
    ).toHaveAttribute("href", "/app/upload");
  });
  it("renders multiple report choices without silently navigating", () => {
    mocks.data = {
      uploads: [],
      eligible: [choice("u1"), choice("u2")],
      nextCursor: null,
    };
    render(<ConnectIdentityPage />);
    expect(
      screen.getAllByRole("link", { name: /choose this report/i }),
    ).toHaveLength(2);
    expect(mocks.replace).not.toHaveBeenCalled();
  });
  it("redirects the single complete choice from the picker", async () => {
    mocks.data = { uploads: [], eligible: [choice("u1")], nextCursor: null };
    render(<ConnectIdentityPage />);
    await waitFor(() =>
      expect(mocks.replace).toHaveBeenCalledWith(
        "/app/uploads/u1#player-identity",
      ),
    );
  });
  it("does not claim uniqueness while older report pages remain", () => {
    mocks.data = { uploads: [], eligible: [choice("u1")], nextCursor: "older" };
    render(<ConnectIdentityPage />);
    expect(
      screen.getByRole("button", { name: "Load older reports" }),
    ).toBeInTheDocument();
    expect(mocks.replace).not.toHaveBeenCalled();
  });
  it("offers upload when processed rows cannot be linked", () => {
    render(<ConnectIdentityPage />);
    expect(
      screen.getByText("No suitable processed report yet"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Upload a GPS report" }),
    ).toBeInTheDocument();
  });
});
