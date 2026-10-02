import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppFrame } from "@/components/layout/app-frame";

const mocks = vi.hoisted(() => ({
  replace: vi.fn(),
  signOut: vi.fn().mockResolvedValue(undefined),
  session: null as object | null,
  api: { me: vi.fn(), players: vi.fn(), teams: vi.fn() },
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mocks.replace }),
  usePathname: () => "/app",
}));
vi.mock("@/lib/auth/provider", () => ({
  authConfigured: true,
  useAuth: () => ({
    session: mocks.session,
    loading: false,
    api: mocks.api,
    signOut: mocks.signOut,
  }),
}));
beforeEach(() => {
  mocks.replace.mockReset();
  mocks.signOut.mockClear();
  mocks.session = { user: { id: "synthetic-user" } };
  mocks.api.me.mockResolvedValue({
    user_id: "synthetic-user",
    profile: { display_name: "Synthetic Player", timezone: "UTC" },
  });
  mocks.api.players.mockResolvedValue({
    items: [
      {
        id: "p1",
        display_name: "Synthetic Player",
        owner_user_id: "synthetic-user",
        created_at: "2026-01-01",
      },
    ],
  });
  mocks.api.teams.mockResolvedValue({ items: [] });
});
afterEach(cleanup);
describe("authenticated shell", () => {
  it("redirects signed-out users to sign-in", async () => {
    mocks.session = null;
    render(
      <AppFrame>
        <div>Private dashboard</div>
      </AppFrame>,
    );
    await waitFor(() =>
      expect(mocks.replace).toHaveBeenCalledWith("/auth/sign-in"),
    );
    expect(screen.queryByText("Private dashboard")).not.toBeInTheDocument();
  });
  it("loads identity, renders navigation, and signs out", async () => {
    render(
      <AppFrame>
        <div>Private dashboard</div>
      </AppFrame>,
    );
    expect(await screen.findByText("Private dashboard")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /my sessions/i })).toHaveAttribute(
      "href",
      "/app/sessions",
    );
    expect(screen.getByRole("link", { name: /my dashboard/i })).toHaveAttribute(
      "href",
      "/app",
    );
    fireEvent.click(screen.getByRole("button", { name: /sign out/i }));
    await waitFor(() => expect(mocks.signOut).toHaveBeenCalledTimes(1));
  });
  it("shows explicit onboarding when there is no player profile", async () => {
    mocks.api.players.mockResolvedValue({ items: [] });
    render(
      <AppFrame>
        <div>Private dashboard</div>
      </AppFrame>,
    );
    expect(
      await screen.findByText("Set up your workspace"),
    ).toBeInTheDocument();
    expect(screen.queryByText("Private dashboard")).not.toBeInTheDocument();
  });
});
