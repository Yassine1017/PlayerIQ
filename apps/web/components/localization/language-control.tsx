"use client";
import { Languages } from "lucide-react";
import { useId } from "react";
import { locales, supportedLocale } from "@/lib/i18n/locale";
import { useLocale } from "./locale-provider";
export function LanguageControl() {
  const id = useId();
  const { locale, tr, setLocale } = useLocale();
  return (
    <div className="theme-control language-control">
      <Languages size={17} aria-hidden="true" />
      <label className="sr-only" htmlFor={id}>
        {tr("Language")}
      </label>
      <select
        id={id}
        title={tr("Language: {language}", { language: locales[locale].name })}
        value={locale}
        onChange={(event) => setLocale(supportedLocale(event.target.value))}
      >
        {Object.entries(locales).map(([key, entry]) => (
          <option key={key} value={key} lang={key} dir={entry.direction}>
            {entry.name}
          </option>
        ))}
      </select>
    </div>
  );
}
