import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import AnalyticsPage from "@/app/app/analytics/page";
import { fact } from "./fixtures";

const mocks = vi.hoisted(() => ({ useResource: vi.fn() }));
vi.mock("@/components/layout/app-frame", () => ({
  useApp: () => ({ player: { id: "p1", display_name: "Synthetic Player" } }),
}));
vi.mock("@/lib/auth/provider", () => ({
  useAuth: () => ({ api: {} }),
}));
vi.mock("@/lib/data/use-resource", () => ({
  useResource: (key: string) => mocks.useResource(key),
}));
afterEach(cleanup);
it("renders backend rule version, record facts, and explicit insufficient trend", () => {
  mocks.useResource.mockImplementation((key: string) => ({
    data: key.startsWith("analytics-overview")
      ? {
          player_id: "p1",
          history_fingerprint: "synthetic-fingerprint",
          rule_version: "analytics_v1",
          facts: [
            {
              ...fact,
              metric_key: "maximum_velocity_kmh",
              value: "31.2",
              unit: "km/h",
              kind: "personal_record",
            },
            { ...fact, kind: "personal_record" },
          ],
        }
      : key.startsWith("analytics-trend")
        ? {
            ...fact,
            kind: "trend",
            status: "insufficient_history",
            points: [],
            sample_size: 1,
          }
        : {
            history_fingerprint: "synthetic-fingerprint",
            rule_version: "analytics_v1",
            items: [],
          },
    error: null,
    loading: false,
    refresh: vi.fn(),
  }));
  render(<AnalyticsPage />);
  expect(screen.getAllByText("analytics_v1").length).toBeGreaterThan(0);
  expect(screen.getByText("31.2 km/h")).toBeInTheDocument();
  expect(screen.getAllByText(/more history needed/i).length).toBeGreaterThan(0);
  expect(screen.getByText(/No workload facts yet/)).toBeInTheDocument();
});
it("shows backend workload outlier evidence and nonmedical explanation", () => {
  mocks.useResource.mockImplementation((key: string) => ({
    data: key.startsWith("analytics-overview")
      ? {
          player_id: "p1",
          history_fingerprint: "synthetic",
          rule_version: "analytics_v1",
          facts: [],
        }
      : key.startsWith("analytics-trend")
        ? { ...fact, kind: "trend", status: "missing_metric", points: [] }
        : {
            history_fingerprint: "synthetic",
            rule_version: "analytics_v1",
            items: [
              {
                ...fact,
                kind: "workload_outlier",
                status: "ok",
                note: "high",
                metric_key: "total_distance_m",
                value: "9100",
                median_value: "7000",
                mad: "400",
                score: "3.8",
                sample_size: 6,
              },
              {
                ...fact,
                kind: "workload_outlier",
                status: "insufficient_history",
                note: "insufficient_variation",
                metric_key: "reported_high_speed_distance_m",
                value: "1200",
                median_value: "1200",
                mad: "0",
                score: null,
                sample_size: 6,
              },
            ],
          },
    error: null,
    loading: false,
    refresh: vi.fn(),
  }));
  render(<AnalyticsPage />);
  expect(screen.getByText("Higher than usual")).toBeInTheDocument();
  expect(screen.getByText(/No spread in prior values/)).toBeInTheDocument();
  expect(screen.getByText("3.8")).toBeInTheDocument();
  expect(
    screen.getByText(/not a medical or injury assessment/i),
  ).toBeInTheDocument();
});
