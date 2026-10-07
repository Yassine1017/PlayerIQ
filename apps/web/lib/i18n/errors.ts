import type { TranslationKey } from "./index";
const messages: Record<string, TranslationKey> = {
  network_error:
    "Could not reach PlayerIQ. Check your connection and try again.",
  unauthorized: "Your session has expired. Please sign in again.",
  forbidden: "You do not have access to this resource.",
  not_found: "This item is unavailable.",
  validation_error: "Check the submitted values and try again.",
  invalid_request: "Check the submitted values and try again.",
  identity_conflict:
    "This action conflicts with the current data. Refresh and try again.",
  identity_confirmation_failed:
    "The session was linked, but your identity connection could not be confirmed. Refresh and try again.",
  conflict:
    "This action conflicts with the current data. Refresh and try again.",
  rate_limited: "Too many requests. Please try again later.",
  ai_budget_exhausted:
    "AI Analyst is temporarily unavailable because this month's AI usage limit has been reached.",
  invalid_credentials: "Invalid email or password.",
  email_not_confirmed: "Confirm your email before signing in.",
  weak_password: "Choose a stronger password.",
};
export function errorKey(error: unknown): TranslationKey {
  const code =
    error && typeof error === "object" && "code" in error ? error.code : null;
  return typeof code === "string" && Object.hasOwn(messages, code)
    ? (messages[code] ?? "Something went wrong. Please try again.")
    : "Something went wrong. Please try again.";
}
export function requestReference(error: unknown): string | undefined {
  return error &&
    typeof error === "object" &&
    "requestId" in error &&
    typeof error.requestId === "string"
    ? error.requestId
    : undefined;
}
