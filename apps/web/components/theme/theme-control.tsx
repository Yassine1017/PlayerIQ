"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useId } from "react";
import { useTheme } from "./theme-provider";
import type { ThemePreference } from "@/lib/theme";

export function ThemeControl() {
  const id = useId();
  const { preference, setPreference } = useTheme();
  const Icon =
    preference === "light" ? Sun : preference === "dark" ? Moon : Monitor;
  const label =
    preference === "light"
      ? "Light"
      : preference === "dark"
        ? "Dark"
        : "System";
  return (
    <div className="theme-control">
      <Icon size={17} aria-hidden="true" />
      <label className="sr-only" htmlFor={id}>
        Appearance
      </label>
      <select
        id={id}
        title={`Appearance: ${label}`}
        value={preference}
        onChange={(event) =>
          setPreference(event.target.value as ThemePreference)
        }
      >
        <option value="light">Light</option>
        <option value="dark">Dark</option>
        <option value="system">System</option>
      </select>
    </div>
  );
}
