"use client";

import { createContext, useContext, useSyncExternalStore } from "react";
import {
  getThemePreference,
  setThemePreference,
  subscribeTheme,
  type ThemePreference,
} from "@/lib/theme";

const ThemeContext = createContext<ThemePreference>("system");
const serverPreference = (): ThemePreference => "system";

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const preference = useSyncExternalStore(
    subscribeTheme,
    getThemePreference,
    serverPreference,
  );
  return (
    <ThemeContext.Provider value={preference}>{children}</ThemeContext.Provider>
  );
}

export function useTheme() {
  return {
    preference: useContext(ThemeContext),
    setPreference: setThemePreference,
  };
}
