import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ChartEditor } from "@/components/uploads/chart-editor";
import type { ChartReview } from "@/lib/api/types";
import { row } from "./fixtures";

const api = vi.hoisted(() => ({
  proposeChart: vi.fn(),
  confirmChart: vi.fn(),
}));
vi.mock("@/lib/auth/provider", () => ({ useAuth: () => ({ api }) }));
const review: ChartReview = {
  id: "review-1",
  source_athlete_row_id: "r1",
  metric_key: "maximum_velocity_kmh",
  raw_label: "31.2",
  parsed_value: "31.2",
  unit: "km/h",
  source_locator: "page:2/chart:maximum_velocity_kmh/table_row_ordinal:3",
  capture_method: "manual",
  status: "proposed",
  proposed_by_user_id: "synthetic-user",
  reviewed_by_user_id: null,
  reviewed_at: null,
  review_reason: null,
  source_observation_id: null,
  created_at: "2026-02-01T00:00:00Z",
};
beforeEach(() => {
  api.proposeChart.mockReset().mockResolvedValue(review);
  api.confirmChart
    .mockReset()
    .mockResolvedValue({ ...review, status: "confirmed" });
});
afterEach(cleanup);
describe("manual chart review", () => {
  it("proposes an exact label and never automatically confirms it", async () => {
    const onUpdate = vi.fn();
    render(
      <ChartEditor uploadId="u1" row={row} reviews={[]} onUpdate={onUpdate} />,
    );
    fireEvent.change(screen.getAllByLabelText("Printed numeric label")[0], {
      target: { value: "31.2" },
    });
    fireEvent.click(
      screen.getAllByRole("button", { name: /propose label/i })[0],
    );
    await waitFor(() =>
      expect(api.proposeChart).toHaveBeenCalledWith(
        "u1",
        "r1",
        "maximum_velocity_kmh",
        "31.2",
      ),
    );
    expect(api.confirmChart).not.toHaveBeenCalled();
    expect(onUpdate).toHaveBeenCalled();
  });
  it("requires explicit athlete and printed-value confirmation", async () => {
    render(
      <ChartEditor
        uploadId="u1"
        row={row}
        reviews={[review]}
        onUpdate={vi.fn()}
      />,
    );
    const button = screen.getByRole("button", { name: /confirm exact label/i });
    expect(button).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(button);
    await waitFor(() =>
      expect(api.confirmChart).toHaveBeenCalledWith("u1", review),
    );
  });
  it("warns on suspicious speed without clipping the printed label", () => {
    render(
      <ChartEditor
        uploadId="u1"
        row={row}
        reviews={[{ ...review, raw_label: "95.8" }]}
        onUpdate={vi.fn()}
      />,
    );
    expect(screen.getByText(/unusually high/)).toBeInTheDocument();
    expect(screen.getByText("95.8")).toBeInTheDocument();
  });
  it("explains unknown Player Load definition and a held value", () => {
    render(
      <ChartEditor
        uploadId="u1"
        row={row}
        reviews={[
          { ...review, status: "held" },
          {
            ...review,
            id: "review-2",
            metric_key: "player_load_reported",
            raw_label: "530",
            status: "confirmed",
          },
        ]}
        onUpdate={vi.fn()}
      />,
    );
    expect(
      screen.getByText(/source formula and unit definition are unknown/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/held from analytics/i)).toBeInTheDocument();
  });
  it("shows a confirmation failure and leaves the proposal pending", async () => {
    api.confirmChart.mockRejectedValue(new Error("Review conflict"));
    render(
      <ChartEditor
        uploadId="u1"
        row={row}
        reviews={[review]}
        onUpdate={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(
      screen.getByRole("button", { name: /confirm exact label/i }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Something went wrong. Please try again.",
    );
    expect(screen.getByText("31.2")).toBeInTheDocument();
  });
  it("shows an already confirmed value without asking for reconfirmation", () => {
    render(
      <ChartEditor
        uploadId="u1"
        row={row}
        reviews={[{ ...review, status: "confirmed" }]}
        onUpdate={vi.fn()}
      />,
    );
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.getByText(/manually confirmed/i)).toBeInTheDocument();
  });
  it("shows automatic evidence and keeps manual correction available", () => {
    render(
      <ChartEditor
        uploadId="u1"
        row={{
          ...row,
          metrics: [
            ...row.metrics,
            {
              source_label: "Maximum Velocity",
              raw_value: "29.75",
              raw_unit: "km/h",
              parsed_value: "29.75",
              quality_state: "accepted",
              source_locator:
                "p2 chart:maximum_velocity method:ocr confidence:0.99",
            },
            {
              source_label: "Player Load",
              raw_value: "420",
              raw_unit: null,
              parsed_value: "420",
              quality_state: "needs_review",
              source_locator: "p2 chart:player_load method:ocr confidence:0.91",
            },
          ],
        }}
        reviews={[]}
        onUpdate={vi.fn()}
      />,
    );
    expect(screen.getByText("29.75")).toBeInTheDocument();
    expect(screen.getByText("420")).toBeInTheDocument();
    expect(screen.getByText(/Automatically extracted/)).toBeInTheDocument();
    expect(screen.getByText(/held from analytics/)).toBeInTheDocument();
    expect(
      screen.getAllByRole("button", {
        name: /review or correct printed value/i,
      }),
    ).toHaveLength(2);
    expect(api.confirmChart).not.toHaveBeenCalled();
  });
});
