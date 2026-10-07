"use client";
import {
  createContext,
  useContext,
  useMemo,
  useSyncExternalStore,
} from "react";
import {
  getLocale,
  setLocale,
  subscribeLocale,
  type Locale,
} from "@/lib/i18n/locale";
import {
  interfaceText,
  translate,
  type TranslationKey,
  type Params,
} from "@/lib/i18n";
const Context = createContext<Locale>("en");
const serverLocale = (): Locale => "en";
export function LocaleProvider({ children }: { children: React.ReactNode }) {
  const locale = useSyncExternalStore(subscribeLocale, getLocale, serverLocale);
  return <Context.Provider value={locale}>{children}</Context.Provider>;
}
export function useLocale() {
  const locale = useContext(Context);
  return useMemo(
    () => ({
      locale,
      setLocale,
      tr: (key: TranslationKey, params?: Params) =>
        translate(locale, key, params),
      ui: (text: string | Error) => interfaceText(locale, text),
    }),
    [locale],
  );
}
