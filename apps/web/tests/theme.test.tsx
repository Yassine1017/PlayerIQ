import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ThemeProvider } from "@/components/theme/theme-provider";
import { ThemeControl } from "@/components/theme/theme-control";
import { THEME_BOOTSTRAP, THEME_KEY } from "@/lib/theme";

let systemDark = false;
let listeners: Set<() => void>;
function bootstrap() {
  // Exercise the exact static code emitted before hydration, not a substitute.
  window.eval(THEME_BOOTSTRAP);
}
function renderControl() {
  return render(
    <ThemeProvider>
      <ThemeControl />
    </ThemeProvider>,
  );
}
function changeSystem(dark: boolean) {
  act(() => {
    systemDark = dark;
    listeners.forEach((listener) => listener());
  });
}
beforeEach(() => {
  localStorage.clear();
  delete document.documentElement.dataset.theme;
  delete document.documentElement.dataset.themePreference;
  systemDark = false;
  listeners = new Set();
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({
      get matches() {
        return systemDark;
      },
      addEventListener: (_: string, listener: () => void) =>
        listeners.add(listener),
      removeEventListener: (_: string, listener: () => void) =>
        listeners.delete(listener),
    })),
  );
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("application appearance", () => {
  it("defaults to System and resolves the operating-system preference before hydration", () => {
    systemDark = true;
    bootstrap();
    expect(document.documentElement.dataset.theme).toBe("dark");
    renderControl();
    expect(screen.getByRole("combobox", { name: "Appearance" })).toHaveValue(
      "system",
    );
    changeSystem(false);
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(localStorage.getItem(THEME_KEY)).toBeNull();
  });
  it("supports Light and Dark and retains only the appearance choice", () => {
    bootstrap();
    renderControl();
    const select = screen.getByRole("combobox", { name: "Appearance" });
    expect(
      screen.getAllByRole("option").map((option) => option.textContent),
    ).toEqual(["Light", "Dark", "System"]);
    select.focus();
    expect(select).toHaveFocus();
    fireEvent.change(select, { target: { value: "dark" } });
    expect(select).toHaveValue("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(localStorage.getItem(THEME_KEY)).toBe("dark");
    expect(localStorage.length).toBe(1);
    fireEvent.change(select, { target: { value: "light" } });
    expect(document.documentElement.dataset.theme).toBe("light");
  });
  it("preserves explicit Dark across remount and a simulated full reload", () => {
    bootstrap();
    const view = renderControl();
    fireEvent.change(screen.getByLabelText("Appearance"), {
      target: { value: "dark" },
    });
    view.unmount();
    delete document.documentElement.dataset.theme;
    delete document.documentElement.dataset.themePreference;
    bootstrap();
    expect(document.documentElement.dataset.theme).toBe("dark");
    renderControl();
    expect(screen.getByLabelText("Appearance")).toHaveValue("dark");
  });
  it("does not override explicit Light or Dark when the OS changes", () => {
    bootstrap();
    renderControl();
    fireEvent.change(screen.getByLabelText("Appearance"), {
      target: { value: "light" },
    });
    changeSystem(true);
    expect(document.documentElement.dataset.theme).toBe("light");
    fireEvent.change(screen.getByLabelText("Appearance"), {
      target: { value: "dark" },
    });
    changeSystem(false);
    expect(document.documentElement.dataset.theme).toBe("dark");
    fireEvent.change(screen.getByLabelText("Appearance"), {
      target: { value: "system" },
    });
    expect(document.documentElement.dataset.theme).toBe("light");
    changeSystem(true);
    expect(document.documentElement.dataset.theme).toBe("dark");
  });
  it("fails safely when storage reads and writes are blocked, preserving a document choice", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("Blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("Blocked");
    });
    systemDark = true;
    expect(bootstrap).not.toThrow();
    const view = renderControl();
    fireEvent.change(screen.getByLabelText("Appearance"), {
      target: { value: "light" },
    });
    expect(document.documentElement.dataset.theme).toBe("light");
    view.unmount();
    renderControl();
    expect(screen.getByLabelText("Appearance")).toHaveValue("light");
    changeSystem(true);
    expect(document.documentElement.dataset.theme).toBe("light");
  });
  it("ignores invalid stored preferences and works without matchMedia", () => {
    localStorage.setItem(THEME_KEY, "untrusted-value");
    vi.stubGlobal("matchMedia", undefined);
    bootstrap();
    renderControl();
    expect(screen.getByLabelText("Appearance")).toHaveValue("system");
    expect(document.documentElement.dataset.theme).toBe("light");
    fireEvent.change(screen.getByLabelText("Appearance"), {
      target: { value: "dark" },
    });
    expect(document.documentElement.dataset.theme).toBe("dark");
  });
  it("synchronizes appearance across tabs and ignores unrelated storage keys", () => {
    bootstrap();
    renderControl();
    act(() => {
      window.dispatchEvent(
        new StorageEvent("storage", { key: THEME_KEY, newValue: "dark" }),
      );
    });
    expect(screen.getByLabelText("Appearance")).toHaveValue("dark");
    act(() => {
      window.dispatchEvent(
        new StorageEvent("storage", {
          key: "other-setting",
          newValue: "light",
        }),
      );
    });
    expect(document.documentElement.dataset.theme).toBe("dark");
    act(() => {
      window.dispatchEvent(
        new StorageEvent("storage", { key: null, newValue: null }),
      );
    });
    expect(screen.getByLabelText("Appearance")).toHaveValue("system");
  });
  it("cleans up the global listeners when the provider unmounts", () => {
    bootstrap();
    const view = renderControl();
    expect(listeners.size).toBe(1);
    view.unmount();
    expect(listeners.size).toBe(0);
  });
});
