"use client";

import { Monitor } from "lucide-react";
import { useId } from "react";
import { useTheme } from "./theme-provider";
import type { ThemePreference } from "@/lib/theme";

export function ThemeControl() {
  const id = useId();
  const { preference, setPreference } = useTheme();
  return (
    <div className="theme-control">
      <Monitor size={15} aria-hidden="true" />
      <label className="sr-only" htmlFor={id}>
        Appearance
      </label>
      <select
        id={id}
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
