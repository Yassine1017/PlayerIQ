import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MyTeamComparisonPanel } from "@/components/team/my-comparison";
import type { MyTeamComparison, PeerComparison } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({ api: { myTeamComparison: vi.fn() } }));
vi.mock("@/lib/auth/provider", () => ({ useAuth: () => ({ api: mocks.api }) }));
const metric: PeerComparison = {
  metric_key: "total_distance_m",
  status: "ok",
  unit: "m",
  your_value: "3500",
  your_display_value: "3500",
  teammate_mean: "3000",
  teammate_display_mean: "3000",
  absolute_difference: "500",
  display_absolute_difference: "+500",
  percentage_difference: "16.66666666666666666666666667",
  display_percentage_difference: "+16.6667",
  direction: "above",
  teammate_sample_size: 5,
  minimum_teammates: 5,
  comparison_scope: "same_report",
  rule_version: "analytics_v1",
};
function data(metrics: PeerComparison[] = [metric]): MyTeamComparison {
  return {
    report_upload_id: "report-1",
    status: "ok",
    rule_version: "analytics_v1",
    metrics,
  };
}
beforeEach(() => {
  mocks.api.myTeamComparison.mockReset().mockResolvedValue(data());
});
afterEach(cleanup);

describe("anonymous teammate comparison", () => {
  it("shows backend values, explicit self exclusion, count and signed differences", async () => {
    render(<MyTeamComparisonPanel teamId="team-1" reportId="report-1" />);
    expect(await screen.findByText("3,500 m")).toBeInTheDocument();
    expect(screen.getByText("3,000 m")).toBeInTheDocument();
    expect(screen.getByText("+500 m")).toBeInTheDocument();
    expect(screen.getByText("+16.6667%")).toBeInTheDocument();
    expect(screen.getByText("Above teammate average")).toBeInTheDocument();
    expect(
      screen.getByText("5 eligible teammates · you excluded"),
    ).toBeInTheDocument();
    expect(screen.getByText(/Your value is excluded/)).toBeInTheDocument();
    expect(mocks.api.myTeamComparison).toHaveBeenCalledWith(
      "team-1",
      "report-1",
      expect.any(AbortSignal),
    );
    expect(screen.queryByText(/better|rank|injury/i)).not.toBeInTheDocument();
  });
  it("uses backend display facts without recomputing or inferring direction", async () => {
    mocks.api.myTeamComparison.mockResolvedValue(
      data([
        {
          ...metric,
          your_value: "9000",
          teammate_mean: "1000",
          display_absolute_difference: "-500",
          display_percentage_difference: "-25.0000",
          direction: "below",
        },
      ]),
    );
    render(<MyTeamComparisonPanel teamId="team-1" reportId="report-1" />);
    expect(
      await screen.findByText("Below teammate average"),
    ).toBeInTheDocument();
    expect(screen.getByText("-500 m")).toBeInTheDocument();
    expect(screen.getByText("-25.0000%")).toBeInTheDocument();
  });
  it("keeps zero mean and zero difference distinct from missing percentages", async () => {
    mocks.api.myTeamComparison.mockResolvedValue(
      data([
        {
          ...metric,
          your_display_value: "0",
          teammate_display_mean: "0",
          display_absolute_difference: "0",
          display_percentage_difference: null,
          direction: "equal",
        },
      ]),
    );
    render(<MyTeamComparisonPanel teamId="team-1" reportId="report-1" />);
    expect(
      await screen.findByText("Equal to teammate average"),
    ).toBeInTheDocument();
    expect(screen.getAllByText("0 m")).toHaveLength(3);
    expect(screen.getByText(/teammate average is zero/)).toBeInTheDocument();
  });
  it("renders insufficient cohorts, missing and incompatible metrics separately", async () => {
    mocks.api.myTeamComparison.mockResolvedValue(
      data([
        {
          ...metric,
          status: "insufficient_cohort",
          teammate_sample_size: 4,
          teammate_display_mean: null,
        },
        {
          ...metric,
          metric_key: "maximum_velocity_kmh",
          status: "missing_metric",
          your_display_value: null,
          teammate_display_mean: null,
        },
        {
          ...metric,
          metric_key: "player_load_reported",
          status: "not_comparable",
          teammate_display_mean: null,
        },
      ]),
    );
    render(<MyTeamComparisonPanel teamId="team-1" reportId="report-1" />);
    expect(
      await screen.findByText(/At least 5 eligible teammates are needed/),
    ).toBeInTheDocument();
    expect(
      screen.getByText("4 eligible teammates · you excluded"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Your accepted metric is unavailable."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Source definitions or participant values/),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Reported index · same activity only."),
    ).toBeInTheDocument();
    expect(screen.queryByText("+16.6667%")).not.toBeInTheDocument();
  });
  it.each([
    ["not_participating", "You have no accepted session in this activity."],
    ["no_player_association", "No verified player association for this team."],
  ] as const)(
    "explains %s without substituting an earlier session",
    async (status, message) => {
      mocks.api.myTeamComparison.mockResolvedValue({ ...data(), status });
      render(
        <MyTeamComparisonPanel teamId="team-1" reportId="report-1" compact />,
      );
      expect(await screen.findByText(message)).toHaveAttribute(
        "role",
        "status",
      );
      expect(screen.queryByText("3,500 m")).not.toBeInTheDocument();
      expect(
        screen.getByRole("link", { name: /Open this activity/ }),
      ).toHaveAttribute("href", "/app/team/sessions/report-1");
    },
  );
  it("refreshes corrected facts from the same endpoint", async () => {
    mocks.api.myTeamComparison
      .mockResolvedValueOnce(data())
      .mockResolvedValueOnce(
        data([{ ...metric, teammate_display_mean: "3100" }]),
      );
    render(<MyTeamComparisonPanel teamId="team-1" reportId="report-1" />);
    await screen.findByText("3,000 m");
    fireEvent.click(
      screen.getByRole("button", { name: "Refresh teammate comparison" }),
    );
    expect(await screen.findByText("3,100 m")).toBeInTheDocument();
    expect(mocks.api.myTeamComparison).toHaveBeenCalledTimes(2);
  });
  it("shows loading and retryable errors without invented values", async () => {
    mocks.api.myTeamComparison.mockRejectedValueOnce(
      new Error("Comparison unavailable"),
    );
    render(<MyTeamComparisonPanel teamId="team-1" reportId="report-1" />);
    expect(
      screen.getByText("Loading your teammate comparison…"),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("Comparison unavailable"),
    ).toBeInTheDocument();
    mocks.api.myTeamComparison.mockResolvedValueOnce(data());
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("3,500 m")).toBeInTheDocument();
  });
  it("does not retain one team's comparison when switching teams", async () => {
    const view = render(
      <MyTeamComparisonPanel teamId="team-1" reportId="report-1" />,
    );
    await screen.findByText("3,500 m");
    mocks.api.myTeamComparison.mockImplementation(() => new Promise(() => {}));
    view.rerender(
      <MyTeamComparisonPanel teamId="team-2" reportId="report-2" />,
    );
    await waitFor(() =>
      expect(screen.queryByText("3,500 m")).not.toBeInTheDocument(),
    );
    expect(
      within(
        screen.getByRole("region", { name: "You versus teammates" }),
      ).getByText(/Loading/),
    ).toBeInTheDocument();
  });
});
