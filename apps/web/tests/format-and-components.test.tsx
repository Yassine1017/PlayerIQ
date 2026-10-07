import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MetricCards } from "@/components/dashboard/metric-card";
import { SessionTable } from "@/components/sessions/session-table";
import { Status } from "@/components/ui/status";
import { TrendChart } from "@/components/analytics/trend-chart";
import { comparisonCopy, metricDisplay, statusText } from "@/lib/format";
import { validatePdf, MAX_PDF_BYTES } from "@/lib/upload";
import { fact, playerSession } from "./fixtures";

afterEach(cleanup);
describe("report file validation", () => {
  it("accepts PDFs and rejects wrong type, empty files, and oversized files", () => {
    expect(
      validatePdf(
        new File(["%PDF"], "synthetic.pdf", { type: "application/pdf" }),
      ),
    ).toBeNull();
    expect(
      validatePdf(new File(["text"], "bad.txt", { type: "text/plain" })),
    ).toMatch(/PDF/);
    expect(
      validatePdf(new File([], "empty.pdf", { type: "application/pdf" })),
    ).toMatch(/empty/);
    const large = new File(["x"], "large.pdf", { type: "application/pdf" });
    Object.defineProperty(large, "size", { value: MAX_PDF_BYTES + 1 });
    expect(validatePdf(large)).toMatch(/10 MB/);
  });
});
describe("grounded metric presentation", () => {
  it("distinguishes missing from printed zero", () => {
    expect(metricDisplay(null, "m")).toBe("—");
    expect(metricDisplay("0", "m")).toBe("0 m");
  });
  it("uses workload language for distance and speed language for velocity", () => {
    expect(comparisonCopy(fact, true)).toContain("workload vs previous 5");
    expect(
      comparisonCopy({ ...fact, metric_key: "maximum_velocity_kmh" }, false),
    ).toContain("speed vs previous 5");
  });
  it("shows explicit unavailable states", () => {
    expect(statusText("insufficient_history")).toBe("More history needed");
    expect(statusText("not_comparable")).toBe("Not comparable");
    expect(statusText("ambiguous_order")).toBe("Session order unclear");
    render(
      <>
        <Status value="zero_recorded" />
        <Status value="held" />
      </>,
    );
    expect(screen.getByText("Zero activity recorded")).toBeInTheDocument();
    expect(screen.getByText("Held for review")).toBeInTheDocument();
  });
  it("renders accepted values and status rather than made-up chart metrics", () => {
    render(
      <MetricCards
        sessions={[playerSession]}
        facts={[
          fact,
          {
            ...fact,
            metric_key: "maximum_velocity_kmh",
            percent_change: null,
            status: "not_comparable",
          },
        ]}
      />,
    );
    expect(screen.getByText("8,400 m")).toBeInTheDocument();
    expect(
      screen.getByText("+12.0% workload vs previous 5"),
    ).toBeInTheDocument();
    expect(screen.getByText("31.2 km/h")).toBeInTheDocument();
    expect(screen.getAllByText("—")).toHaveLength(2);
    expect(screen.getByText("Not comparable")).toBeInTheDocument();
  });
  it("does not choose an arbitrary latest session when dates tie", () => {
    render(
      <MetricCards
        sessions={[playerSession, { ...playerSession, id: "s2" }]}
        facts={[fact]}
      />,
    );
    expect(screen.getAllByText("Latest session order unclear")).toHaveLength(4);
  });
  it("renders session links with accepted values only", () => {
    render(<SessionTable sessions={[playerSession]} />);
    expect(screen.getByText("8,400 m")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /view/i })).toHaveAttribute(
      "href",
      "/app/sessions/s1",
    );
    expect(screen.getByText("—")).toBeInTheDocument();
  });
  it("offers chart data as an accessible table and preserves session type", () => {
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    );
    render(
      <TrendChart
        fact={{
          ...fact,
          kind: "trend",
          points: [
            {
              session_id: "s1",
              local_date: "2026-02-01",
              session_type: "training",
              value: "8400",
              source_observation_id: "o1",
            },
          ],
        }}
      />,
    );
    fireEvent.click(screen.getByText("View accessible data table"));
    expect(screen.getByRole("table")).toHaveTextContent("Training");
    expect(screen.getByRole("table")).toHaveTextContent("8,400 m");
  });
});
