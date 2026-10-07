import { errorKey, requestReference } from "./errors";
import { en } from "./messages/en";
import { pt } from "./messages/pt-BR";
import { ar } from "./messages/ar";
import type { Locale } from "./locale";
export type TranslationKey = keyof typeof en;
export type Message =
  | string
  | (Partial<Record<Intl.LDMLPluralRule | "other", string>> & {
      other: string;
    });
export type Dictionary = Record<TranslationKey, Message>;
export type Params = Record<string, string | number>;
export const dictionaries: Record<Locale, Dictionary> = { en, "pt-BR": pt, ar };
export function translate(
  locale: Locale,
  key: TranslationKey,
  params: Params = {},
): string {
  let message = dictionaries[locale][key];
  if (!message) {
    if (process.env.NODE_ENV === "development")
      console.warn("PlayerIQ: missing interface translation");
    message = en[key];
  }
  const text =
    typeof message === "string"
      ? message
      : (message[
          new Intl.PluralRules(locale).select(Number(params.count ?? 0))
        ] ?? message.other);
  return text.replace(/\{(\w+)\}/g, (_, name: string) =>
    String(params[name] ?? `{${name}}`),
  );
}
// Only for explicitly identified UI labels (navigation, statuses, local errors).
// Never pass arbitrary report evidence, names, user input or AI prose here.
export function interfaceText(locale: Locale, text: string | Error): string {
  if (text instanceof Error) {
    const reference = requestReference(text);
    return (
      translate(locale, errorKey(text)) +
      (reference
        ? " — " +
          translate(locale, "Request reference: {id}", {
            id: "⁦" + reference + "⁩",
          })
        : "")
    );
  }
  return Object.hasOwn(en, text)
    ? translate(locale, text as TranslationKey)
    : text;
}
