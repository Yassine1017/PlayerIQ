export const locales = {
  en: { name: "English", direction: "ltr" },
  "pt-BR": { name: "Português", direction: "ltr" },
  ar: { name: "العربية", direction: "rtl" },
} as const;
export type Locale = keyof typeof locales;
export const LOCALE_KEY = "playeriq.locale.v1";
export function supportedLocale(value: unknown): Locale {
  return typeof value === "string" && Object.hasOwn(locales, value)
    ? (value as Locale)
    : "en";
}
let current: Locale | undefined;
const eventName = "playeriq:locale";
function apply(locale: Locale) {
  document.documentElement.lang = locale;
  document.documentElement.dir = locales[locale].direction;
}
export function getLocale(): Locale {
  if (typeof window === "undefined") return "en";
  if (current === undefined) {
    try {
      current = supportedLocale(localStorage.getItem(LOCALE_KEY));
    } catch {
      current = "en";
    }
  }
  return current;
}
export function setLocale(locale: Locale) {
  current = supportedLocale(locale);
  try {
    localStorage.setItem(LOCALE_KEY, current);
  } catch {
    /* In-document preference still works. */
  }
  apply(current);
  window.dispatchEvent(new Event(eventName));
}
export function subscribeLocale(listener: () => void) {
  apply(getLocale());
  const changed = () => {
    apply(getLocale());
    listener();
  };
  const storage = (event: StorageEvent) => {
    if (event.key === LOCALE_KEY || event.key === null) {
      current = supportedLocale(event.newValue);
      changed();
    }
  };
  window.addEventListener(eventName, changed);
  window.addEventListener("storage", storage);
  return () => {
    window.removeEventListener(eventName, changed);
    window.removeEventListener("storage", storage);
  };
}
// Static, supported preferences only; independent of authentication and appearance.
export const LOCALE_BOOTSTRAP = `;(function(){var l="en";try{var v=localStorage.getItem("playeriq.locale.v1");if(v==="ar"||v==="pt-BR")l=v}catch(e){}document.documentElement.lang=l;document.documentElement.dir=l==="ar"?"rtl":"ltr"})()`;
