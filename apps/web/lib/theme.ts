export type ThemePreference = "light" | "dark" | "system";
export const THEME_KEY = "playeriq.appearance.v1";
const THEME_EVENT = "playeriq-appearance-change";
const DARK_QUERY = "(prefers-color-scheme: dark)";

function preference(value: string | null | undefined): ThemePreference {
  return value === "light" || value === "dark" ? value : "system";
}

export function getThemePreference(): ThemePreference {
  return preference(document.documentElement.dataset.themePreference);
}

function applyTheme(value: ThemePreference, systemDark: boolean) {
  const root = document.documentElement;
  root.dataset.themePreference = value;
  root.dataset.theme =
    value === "system" ? (systemDark ? "dark" : "light") : value;
}

export function setThemePreference(value: ThemePreference) {
  try {
    localStorage.setItem(THEME_KEY, value);
  } catch {
    // Storage can be blocked; retain the choice in this document for navigation.
  }
  applyTheme(value, window.matchMedia?.(DARK_QUERY).matches ?? false);
  window.dispatchEvent(new Event(THEME_EVENT));
}

export function subscribeTheme(onChange: () => void): () => void {
  const media = window.matchMedia?.(DARK_QUERY);
  const updateSystem = () => {
    applyTheme(getThemePreference(), media?.matches ?? false);
    onChange();
  };
  const updateStorage = (event: StorageEvent) => {
    if (event.key !== THEME_KEY && event.key !== null) return;
    applyTheme(preference(event.newValue), media?.matches ?? false);
    onChange();
  };
  // Preserve the bootstrap's preference, including a choice made while storage
  // is unavailable. Hydration never needs to inspect credentials or Auth state.
  updateSystem();
  media?.addEventListener("change", updateSystem);
  window.addEventListener(THEME_EVENT, onChange);
  window.addEventListener("storage", updateStorage);
  return () => {
    media?.removeEventListener("change", updateSystem);
    window.removeEventListener(THEME_EVENT, onChange);
    window.removeEventListener("storage", updateStorage);
  };
}

// Static first-paint script: no user input, credentials, network calls or eval.
// Keep its behavior aligned with the runtime above; tests exercise both paths.
export const THEME_BOOTSTRAP = `(()=>{let p="system";try{const v=localStorage.getItem("${THEME_KEY}");if(v==="light"||v==="dark")p=v}catch{}const r=document.documentElement;r.dataset.themePreference=p;r.dataset.theme=p==="system"?(window.matchMedia?.("${DARK_QUERY}").matches?"dark":"light"):p})()`;
