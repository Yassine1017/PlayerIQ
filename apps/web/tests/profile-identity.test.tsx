import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import ProfilePage from "@/app/app/profile/page";

const mocks = vi.hoisted(() => ({
  identities: [] as {
    id: string;
    original_label: string;
    confirmed_at: string;
    status: "connected" | "revoked";
  }[],
  revoke: vi.fn(),
  refresh: vi.fn(),
  api: {
    sourceIdentities: vi.fn(),
    revokeSourceIdentity: vi.fn(),
    updateMe: vi.fn(),
  },
}));
vi.mock("@/components/layout/app-frame", () => ({
  useApp: () => ({
    me: {
      user_id: "user-1",
      profile: { display_name: "Alex Morgan", timezone: "UTC" },
    },
    player: { id: "p1", display_name: "Alex Morgan", owner_user_id: "user-1" },
    refreshIdentity: vi.fn(),
  }),
}));
vi.mock("@/lib/auth/provider", () => ({ useAuth: () => ({ api: mocks.api }) }));
vi.mock("@/lib/data/use-resource", () => ({
  useResource: () => ({
    data: { items: mocks.identities },
    loading: false,
    error: null,
    refresh: mocks.refresh,
  }),
}));
beforeEach(() => {
  mocks.identities = [];
  mocks.api.revokeSourceIdentity.mockReset().mockResolvedValue({});
  mocks.refresh.mockReset();
  vi.spyOn(window, "confirm").mockReturnValue(true);
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

it("shows an unconnected identity with a report review path", () => {
  render(<ProfilePage />);
  expect(screen.getByText(/Not connected yet/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /My Reports/ })).toHaveAttribute(
    "href",
    "/app/upload",
  );
});
it("shows confirmed source provenance and revokes only after confirmation", async () => {
  mocks.identities = [
    {
      id: "identity-1",
      original_label: "SYNTHETIC ATHLETE",
      confirmed_at: "2026-02-01T10:00:00Z",
      status: "connected",
    },
  ];
  render(<ProfilePage />);
  expect(screen.getByText("SYNTHETIC ATHLETE")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));
  await waitFor(() =>
    expect(mocks.api.revokeSourceIdentity).toHaveBeenCalledWith("identity-1"),
  );
  expect(mocks.refresh).toHaveBeenCalled();
});
