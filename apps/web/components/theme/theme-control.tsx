"use client";
import { useLocale } from "@/components/localization/locale-provider";

import { Monitor, Moon, Sun } from "lucide-react";
import { useId } from "react";
import { useTheme } from "./theme-provider";
import type { ThemePreference } from "@/lib/theme";

export function ThemeControl() {
  const { tr, ui } = useLocale();

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
        {tr("Appearance")}
      </label>
      <select
        id={id}
        title={tr("Appearance: {appearance}", { appearance: ui(label) })}
        value={preference}
        onChange={(event) =>
          setPreference(event.target.value as ThemePreference)
        }
      >
        <option value="light">{tr("Light")}</option>
        <option value="dark">{tr("Dark")}</option>
        <option value="system">{tr("System")}</option>
      </select>
    </div>
  );
}
