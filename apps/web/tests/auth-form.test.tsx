import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { AuthForm } from "@/components/auth/auth-form";

const mocks = vi.hoisted(() => ({
  replace: vi.fn(),
  signInWithPassword: vi.fn(),
  signUp: vi.fn(),
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mocks.replace }),
}));
vi.mock("@/lib/auth/provider", () => ({
  authConfigured: true,
  supabase: () => ({
    auth: {
      signInWithPassword: mocks.signInWithPassword,
      signUp: mocks.signUp,
    },
  }),
}));
beforeEach(() => {
  mocks.replace.mockReset();
  mocks.signInWithPassword.mockReset().mockResolvedValue({
    data: { session: { access_token: "synthetic" } },
    error: null,
  });
  mocks.signUp.mockReset();
});
afterEach(cleanup);
it("signs in with Supabase and enters the authenticated workspace", async () => {
  render(<AuthForm mode="sign-in" />);
  fireEvent.change(screen.getByLabelText("Email address"), {
    target: { value: "synthetic@example.com" },
  });
  fireEvent.change(screen.getByLabelText("Password"), {
    target: { value: "synthetic-pass" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  await waitFor(() =>
    expect(mocks.signInWithPassword).toHaveBeenCalledWith({
      email: "synthetic@example.com",
      password: "synthetic-pass",
    }),
  );
  expect(mocks.replace).toHaveBeenCalledWith("/app");
});
it("shows authentication errors without entering the app", async () => {
  mocks.signInWithPassword.mockResolvedValue({
    data: { session: null },
    error: { message: "Invalid credentials" },
  });
  render(<AuthForm mode="sign-in" />);
  fireEvent.change(screen.getByLabelText("Email address"), {
    target: { value: "synthetic@example.com" },
  });
  fireEvent.change(screen.getByLabelText("Password"), {
    target: { value: "bad-pass" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Invalid credentials",
  );
  expect(mocks.replace).not.toHaveBeenCalled();
});
