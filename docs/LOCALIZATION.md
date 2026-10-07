# PlayerIQ interface languages

## Supported languages and controls

The interface supports English (`en`, default), Brazilian Portuguese (`pt-BR`) and Modern Standard Arabic (`ar`). Brazilian Portuguese is the first Portuguese variant implemented; it does not imply a player's nationality. European Portuguese can be added independently later.

The 40 × 40 px Languages control sits immediately beside Appearance in the authenticated desktop/mobile header, sign-in, sign-up and initial workspace setup. Identity onboarding uses that same application header. Its native select offers **English**, **Português** and **العربية**, with localized accessible labels, a current-language title, keyboard focus and native touch selection. No flags or localization service are used.

Changing language updates interface text and direction in the current document. It does not reload the application or make an API request. Appearance, authentication, selected team, routes and account identity retain their existing behavior.

## Preferences and rendering

Only the supported locale string is saved under `playeriq.locale.v1` in localStorage, independently of `playeriq.appearance.v1` and authentication storage. Navigation, reload and same-origin tabs retain a successfully saved preference. Unsupported values fall back to English; removing the preference also restores English. Storage events synchronize language changes across tabs and listeners are removed on unmount.

If storage is blocked, the current-document preference still works, including client navigation and provider remounts. A full reload falls back to English. No authentication storage is read by the locale implementation.

`lib/i18n/locale.ts` contains the supported-locale registry, validation, preference store, subscription and static bootstrap. The head bootstrap applies saved `html.lang` and `html.dir` before paint where possible. It follows the existing theme bootstrap with an explicit statement separator. The HTML root retains the existing narrow attribute-mismatch suppression for bootstrap-controlled attributes; descendants are not suppressed.

`LocaleProvider` uses `useSyncExternalStore` with an English server snapshot. The server and first hydration render therefore agree. Saved translations appear after hydration, so a returning user can briefly see English text in the saved direction. There is no initialization-only blank screen. Fully localized server HTML would require a separate server-readable preference design; cookies and locale URLs were not introduced here. A future restrictive CSP must authorize both exact bootstrap scripts with a nonce or hash.

## Dictionaries and keys

- `lib/i18n/messages/en.ts` defines the typed key set and English fallback.
- `pt-BR.ts` and `ar.ts` implement `Dictionary`, requiring the same keys.
- `useLocale()` provides the active locale, typed `tr(key, namedParameters)` and `ui(text)` for explicitly identified internal UI labels.
- Complete English message phrases are keys for existing static copy. Whole sentences with named placeholders replace dynamic sentence fragments. Count messages such as `sessionCount`, `athleteCount`, `rowCount`, `participantCount` and `cohortCount` use `Intl.PluralRules`; Arabic session counts cover zero, one, two, few, many and other.
- Messages contain text only, with no embedded HTML or runtime machine translation. Values are rendered through React text nodes.
- A missing dictionary entry falls back to English and emits a generic development diagnostic without user data. Type checking and tests enforce key, placeholder and nonempty-message parity before release.

`ui` is a compatibility helper for known navigation/metric/status labels and local feedback already represented in the dictionaries. Do not pass names, arbitrary evidence, user text or generated AI prose to it. New fixed copy should use typed `tr` calls; new dynamic UI labels must have dictionary entries.

## Coverage and preserved source content

Localized screens include authentication/setup, navigation, personal dashboard/sessions/detail/profile, analytics filters and summaries, uploads/report review, identity selection/confirmation, chart review, team dashboards/sessions/directories/report summaries, creation/join/approval controls, roster imports and anonymous teammate comparisons. Loading, empty, held/missing/zero states, buttons, tooltips and accessibility labels are included.

AI localization covers the conversation interface, suggested-question labels, fact captions, source links, calculation explanation, status, stale and budget feedback. Suggested labels are translated while their existing canonical English questions are sent unchanged on selection. User-entered questions remain unchanged. Generated answer sentences and existing conversation titles are not translated. Arabic/Portuguese AI answer quality remains a separate verification task; this implementation makes no AI calls and changes no tools, rules, grounding or budget behavior.

Player/team names, filenames, source athlete labels/position codes, exact report metric labels, raw chart labels/locators, source definitions, validation notes and evidence remain original. Technical IDs and `analytics_v1` retain their stored spelling. UI metric captions can be translated, while source-label lookups always use the original GPS labels. Player Load remains a reported index with unknown formula/units, and workload differences retain neutral meaning.

API and Auth errors are translated using an allowlist of stable error codes in `lib/i18n/errors.ts`. Structured errors are retained until display. Arbitrary server message prose is never used to choose a translation and is hidden behind a safe localized fallback. Available request references remain visible, with directional isolation. Source validation notes are evidence and are deliberately kept intact.

## Dates, decimals and RTL

`lib/format.ts` accepts an explicit locale, defaulting to English for existing pure callers. GPS dates use the stored local date portion, the Gregorian calendar, UTC formatting and Latin digits. They do not shift according to the browser time zone. Machine dates and API values are unchanged.

Metric formatting uses decimal strings and BigInt presentation rounding, avoiding conversion of arbitrary-precision facts to JavaScript Number. Existing display precision is retained: whole metres, one fractional speed digit, and up to two digits for other values/source indices. Decimal grouping/separators follow the locale. Printed zero stays zero; null/undefined stay unavailable. Formatting is not used to compute analytics or parse API inputs. Chart coordinates still require floating-point values for plotting; original decimal strings remain authoritative in tooltips and accessible tables, and no analytical calculation occurs in the chart.

Arabic applies `dir="rtl"`; English/Portuguese restore `ltr`. CSS logical properties handle alignment, padding, margins, borders and the mobile sidebar edge. Directional navigation arrows alone are flipped. The logo, photos, PDF evidence and chart chronology are not mirrored. Charts explicitly retain LTR axis/data ordering. Numeric metric/unit pairs use LTR `bdi` elements; names, filenames and technical references use isolation where mixed text appears. Technical form inputs remain LTR. Arabic uses the local Tahoma/Arial font stack without remote font requests.

Long translated headings/actions wrap on narrow screens; tables retain their existing internal horizontal scrolling instead of widening the document. Both preference controls retain their 40 px footprint.

## Adding a language

1. Add its locale, native name and direction to the central registry. Extend bootstrap validation deliberately; never insert arbitrary saved text into a script.
2. Add a dictionary implementing `Dictionary`, including named placeholders and required plural categories.
3. Register the dictionary and review formatting/font/RTL behavior for that locale.
4. Run dictionary parity, preference, formatting and representative screen tests, then desktop/mobile browser checks in both themes.
5. Arrange native-speaker terminology review. Do not use flags or infer language from player nationality.

## Verification and remaining checks

Verification uses synthetic fixtures only. No private PDF, athlete data, credentials or real browser session are required. Browser scripts/screenshots are outside the repository, and external Auth requests are blocked in the isolated fixture.

The implementation is checked with the complete frontend Vitest suite, Prettier, ESLint, TypeScript, production build and `git diff --check`. New tests cover dictionary/placeholder parity, plural categories, preference/default/invalid/blocked behavior, remount/bootstrap/cross-tab behavior, lang/dir restoration, theme independence, selector accessibility, stable-code errors/request references, Gregorian dates, lossless rounding, missing versus zero, translated team states and preservation of GPS lookup labels/chart values in Portuguese/Arabic.

Synthetic Chromium checks cover English Light, Portuguese Dark, Arabic Light and Arabic Dark on desktop 1440 × 1000 and mobile 390 × 844 / 320 × 844. Representative screens are sign-in, dashboard, identity connection/confirmation, upload/review, analytics, team dashboard/session comparison and AI chrome. Checks include 40 px controls, text/direction switching, keyboard focus, navigation/reload persistence, independent theme/language choices, sidebar edges, source-name preservation, document overflow and runtime/hydration errors.

Recorded results on 2026-10-07: **134 tests passed across 19 files**; Prettier, ESLint, TypeScript and the production frontend build passed. Synthetic browser verification passed **32 desktop and 64 mobile route checks** with no runtime/hydration errors during the final runs, plus a focused final Arabic identity/comparison capture. No paid AI calls were made. Earlier QA findings (mobile wrapping, numeric bidirectional isolation and original GPS lookup labels) were corrected before these final checks. Screenshots are retained outside Git in the local temporary QA folder.

Native-speaker review is **pending**; these translations are not professionally certified. Firefox/Safari/native mobile selects and live authenticated E2E are **pending**. Before production use:

1. Ask Portuguese/Arabic football speakers to review terminology, plural phrasing, line breaks and error wording.
2. Repeat the preference/navigation/reload flows in Firefox, Safari and a real mobile browser, including opening native menus and keyboard selection.
3. Using an authorized development account and synthetic reports, check identity confirmation, chart correction, team approval/import, player/manager visibility and source PDF presentation in all languages. Existing acceptance/privacy rules must remain unchanged.
4. View an existing synthetic AI answer and verify original prose/source facts remain intact. Do not generate a paid answer solely to test UI localization.

Backend/API schemas, migrations, RLS, GPS ingestion and `analytics_v1` are unchanged. No deployment or Phase 6 work is included.
