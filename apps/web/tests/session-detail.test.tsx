import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import SessionDetail from "@/app/app/sessions/[sessionId]/page";
import { ApiError } from "@/lib/api/client";
import { playerSession } from "./fixtures";

const mocks = vi.hoisted(() => ({ result: null as unknown }));
vi.mock("next/navigation", () => ({ useParams: () => ({ sessionId: "s1" }) }));
vi.mock("@/components/layout/app-frame", () => ({
  useApp: () => ({ player: { id: "p1", display_name: "Synthetic Player" } }),
}));
vi.mock("@/lib/auth/provider", () => ({ useAuth: () => ({ api: {} }) }));
vi.mock("@/lib/data/use-resource", () => ({ useResource: () => mocks.result }));
afterEach(cleanup);
it("shows accepted session values, missing chart data, and provenance", () => {
  mocks.result = {
    data: playerSession,
    error: null,
    loading: false,
    refresh: vi.fn(),
  };
  render(<SessionDetail />);
  expect(screen.getAllByText("8,400 m").length).toBeGreaterThan(0);
  expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  expect(screen.getByText("r1")).toBeInTheDocument();
  expect(
    screen.getByText(/full team PDF remains private/i),
  ).toBeInTheDocument();
});
it("does not reveal an inaccessible session", () => {
  mocks.result = {
    data: null,
    error: new ApiError("not_found", "Not found", 404),
    loading: false,
    refresh: vi.fn(),
  };
  render(<SessionDetail />);
  expect(screen.getByRole("alert")).toHaveTextContent(
    "unavailable to this account",
  );
  expect(screen.queryByText("8,400 m")).not.toBeInTheDocument();
});
