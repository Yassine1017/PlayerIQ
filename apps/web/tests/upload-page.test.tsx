import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import UploadPage from "@/app/app/upload/page";
import type { Team } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  push: vi.fn(),
  uploadPdf: vi.fn(),
  uploads: vi.fn(),
  refresh: vi.fn(),
  teams: [] as Team[],
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: mocks.push }) }));
vi.mock("@/lib/auth/provider", () => ({
  useAuth: () => ({
    api: { uploadPdf: mocks.uploadPdf, uploads: mocks.uploads },
  }),
}));
vi.mock("@/components/layout/app-frame", () => ({
  useApp: () => ({ teams: mocks.teams }),
}));
vi.mock("@/lib/data/use-resource", () => ({
  useResource: () => ({
    data: {
      items: [
        {
          upload_id: "u1",
          original_filename: "synthetic.pdf",
          status: "awaiting_link",
          created_at: "2026-02-01T00:00:00Z",
          processed_at: null,
          athlete_row_count: 2,
          error_code: null,
        },
      ],
      next_cursor: null,
    },
    loading: false,
    error: null,
    refresh: mocks.refresh,
  }),
}));
beforeEach(() => {
  mocks.teams = [];
  mocks.push.mockReset();
  mocks.uploadPdf
    .mockReset()
    .mockResolvedValue({ upload_id: "u2", status: "queued" });
});
afterEach(cleanup);
it("selects a valid PDF, displays history, and opens the new review page", async () => {
  render(<UploadPage />);
  expect(screen.getByText("synthetic.pdf")).toBeInTheDocument();
  expect(screen.getByText("2")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Select GPS PDF"), {
    target: {
      files: [
        new File(["%PDF"], "new-report.pdf", { type: "application/pdf" }),
      ],
    },
  });
  expect(screen.getByText("new-report.pdf")).toBeInTheDocument();
  fireEvent.click(
    screen.getByRole("button", { name: /upload and process report/i }),
  );
  await waitFor(() => expect(mocks.uploadPdf).toHaveBeenCalled());
  expect(mocks.push).toHaveBeenCalledWith("/app/uploads/u2");
});
it("rejects non-PDF selection before an upload request", () => {
  render(<UploadPage />);
  fireEvent.change(screen.getByLabelText("Select GPS PDF"), {
    target: { files: [new File(["bad"], "bad.txt", { type: "text/plain" })] },
  });
  expect(screen.getByRole("alert")).toHaveTextContent("Choose a PDF");
  expect(mocks.uploadPdf).not.toHaveBeenCalled();
});
it("makes whole-report team sharing explicit and sends the selected session type", async () => {
  mocks.teams = [
    {
      id: "team-synthetic",
      name: "Synthetic FC",
      role: "admin",
      player_id: "self",
      created_at: "2026-01-01",
    },
  ];
  render(<UploadPage />);
  fireEvent.change(screen.getByLabelText(/Report workspace/), {
    target: { value: "team-synthetic" },
  });
  expect(
    screen.getByText(
      /all its identifiable athletes, including nonparticipants/,
    ),
  ).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Team session type"), {
    target: { value: "training" },
  });
  const file = new File(["%PDF"], "synthetic-team.pdf", {
    type: "application/pdf",
  });
  fireEvent.change(screen.getByLabelText("Select GPS PDF"), {
    target: { files: [file] },
  });
  fireEvent.click(
    screen.getByRole("button", { name: /Upload and import team athletes/ }),
  );
  await waitFor(() =>
    expect(mocks.uploadPdf).toHaveBeenCalledWith(
      file,
      expect.any(Function),
      "team-synthetic",
      "training",
    ),
  );
  expect(mocks.push).toHaveBeenCalledWith("/app/uploads/u2");
});
