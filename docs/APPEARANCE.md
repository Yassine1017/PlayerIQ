# PlayerIQ appearance

## Choosing a theme

The compact Appearance control in the application header offers **Light**, **Dark** and **System** on desktop and mobile. A sun, moon or monitor icon shows the selected preference; click/tap it to open the native menu, or use the keyboard. Its accessible name is Appearance, the native select exposes the current value, and its hover title names that preference. The control occupies 40 × 40 px with a visible focus ring. It is also available on sign-in, sign-up and initial workspace setup. System is the default when no valid choice has been saved; operating-system changes update the palette only while System is selected. An explicit Light or Dark selection takes precedence.

Only the string `light`, `dark` or `system` is stored under `playeriq.appearance.v1` in browser localStorage. It is an appearance preference for this browser/origin, shared across its tabs and independent of accounts; no account data or authentication changes are involved. Navigation and reload retain a successfully stored choice. If storage is blocked, theme selection still works for the current document and client navigation; a full reload falls back to System. Invalid stored strings also fall back to System.

## Implementation

- `lib/theme.ts`: preference validation, DOM application, OS/storage listeners and a static first-paint bootstrap.
- `components/theme/theme-provider.tsx`: a small context with `useSyncExternalStore`, a deterministic System server snapshot and listener cleanup. It wraps the existing Auth provider without changing its behavior.
- `components/theme/theme-control.tsx`: a labeled native select with Light/Dark/System options and keyboard/focus support.
- `app/layout.tsx`: the static bootstrap executes in the document head before first paint. Only the root HTML element suppresses the expected theme-attribute hydration mismatch; descendant mismatches remain visible. The script contains no dynamic user input, network access or credentials. A future restrictive CSP must authorize the exact bootstrap with a hash or nonce; this change does not weaken or introduce a CSP.
- `app/globals.css`: semantic variables provide the Light and Soft Graphite palettes. `data-theme` controls the palette and native `color-scheme`; `data-theme-preference` retains the explicit choice. Tailwind semantic utilities share these variables. Appearance is not duplicated in page-specific dark selectors.

Token groups cover canvas/surfaces, text, decorative borders, control borders, accent/foreground, focus, disabled states, status foreground/background, sidebar, chart series/grid and loading skeletons. Use semantic utilities such as `text-content`, `text-muted`, `border-line`, `bg-surface-muted` and `text-accent-text` for new shared UI. Interactive boundaries use `--control-border`; `--line` is a subtler decorative separator, not the sole indicator of an input or button.

## Design and accessibility

Dark mode follows the selected Soft Graphite concept: canvas `#15191D`, sidebar `#111518`, cards `#20262B`, raised surfaces `#293139`, decorative borders `#35404A`, text `#F3F6F8`, secondary text `#A7B4BE`, mint `#63D5B6` and chart series `#82B6E8`. Existing fonts, page structure, navigation, data contracts and imagery remain. The mockup's illustrative data/layout additions were not implemented.

Control borders are stronger than the reference (`#7D8E9B` in Dark, `#7D8E96` in Light) to meet the 3:1 boundary target. Existing Light secondary text is strengthened to `#506772`, and success text to `#087951`, for small-label contrast. Disabled controls use readable muted text rather than reducing the entire control's opacity. Text/icons identify status states, and workload comparisons retain neutral text. Mobile hides the redundant Workspace breadcrumb prefix to keep the current page name and Appearance control readable. Reduced-motion settings disable interface transitions and skeleton animation.

The 18 verified token combinations in each theme cover primary/secondary text on main/card/raised surfaces, accent text, button labels, status text, sidebar labels, controls, focus and chart series. Minimum normal-text contrast is **4.92:1 Light / 6.23:1 Dark**; minimum tested control/focus/series contrast is **3.15:1 Light / 3.90:1 Dark**. These are measured token pairs, not a claim of a complete WCAG certification. Decorative card borders/gridlines and exempt disabled boundaries are not claimed to meet the interactive-boundary threshold.

## Coverage and evidence

Shared tokens cover personal/team dashboards, sessions/detail, anonymous teammate comparisons, player directories, membership forms, upload/status/review, identity onboarding/confirmation, chart review, profile, analytics and AI conversations/fact references/budget states. Existing charts use theme-aware series, axes, grid, dots and tooltips, keeping their accessible data tables and backend facts.

PDF iframes retain a light document canvas. Source PDFs and chart images are never recolored, inverted, filtered or rewritten; only surrounding controls change appearance. There are no new dialogs, toasts, charts, calculations or AI tools.

Verified on 2026-10-04:

- Complete frontend suite: **103 tests passed across 18 files**, including default/explicit/System behavior, persistence, blocked storage, invalid values, cross-tab synchronization, listener cleanup and comparison states with the theme provider.
- Prettier, ESLint, TypeScript and production build passed.
- Isolated synthetic Playwright checks at `http://localhost:3000`, desktop 1440 × 1000 and mobile 390 × 844, verified Light/Dark/System, keyboard selection/focus, navigation/reload persistence, OS changes, chart tooltips, personal/team pages, upload/chart review, identity onboarding, missing/insufficient/error states and mocked AI facts/budget fallback. Browser plugin was unavailable, so the existing Playwright CLI was used. All Auth/API fixtures were fabricated and external Auth requests blocked; no private account session or PDF was inspected.
- The saved Dark preference was present at first paint and first contentful paint after reload. No hydration/framework errors were observed. Mobile pages had no horizontal document overflow. An initial request for the existing missing favicon returned 404; intentional synthetic API error cases also produced expected network errors. These are separate from theme/runtime failures.
- Backend, database, RLS, metric/AI rules and dependencies were unchanged. No migrations, development database writes or paid AI calls were made.

Screenshots and temporary browser scripts remain outside the repository. Live authenticated E2E is pending; the checks above are mocked UI verification.

Compact-control follow-up verified on 2026-10-05: the same 103 tests passed, together with Prettier, ESLint, TypeScript and production build. Isolated synthetic browser checks at desktop 1440 × 1000 and mobile 390 × 844 confirmed the 40 px control, visible keyboard focus, changing icons/menu choices, saved preference after reload, System following OS changes, explicit preference override and no page overflow. The checked team-session interaction produced no page errors or console warnings/errors. Native menu rendering on Firefox/Safari and live authenticated flows remain manual checks. The native menu was also opened by pointer to verify all three choices remain readable.

## Remaining manual checks

Using already available safe development accounts and synthetic data:

1. Select Dark, navigate personal/team pages and reload; confirm the choice persists. Select System and change the OS setting; verify it follows. Repeat with keyboard and on a mobile device.
2. As player and manager, check the existing role-specific tables, approved membership forms, chart review/identity confirmation and empty/error/held states in both themes. Verify the appearance change does not alter visibility or actions.
3. Open an authorized synthetic PDF and chart evidence; verify printed labels/pixels remain intact on the light document canvas with readable surrounding controls.
4. Review an existing synthetic AI answer, source links and budget/unavailable states without generating a paid answer. Check analytics tooltips and the accessible data table in both themes.
5. Check Firefox/Safari and native mobile selects/date inputs. Chromium desktop/mobile emulation was verified; other browser/device rendering was not.

Phase 6 remains future work.
