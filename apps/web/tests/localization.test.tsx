import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { LocaleProvider } from "@/components/localization/locale-provider";
import { LanguageControl } from "@/components/localization/language-control";
import { ThemeProvider } from "@/components/theme/theme-provider";
import { ThemeControl } from "@/components/theme/theme-control";
import { ErrorState } from "@/components/ui/states";
import { TeamAverageCard } from "@/components/team/team-average";
import { Status } from "@/components/ui/status";
import { ApiError } from "@/lib/api/client";
import { dictionaries, translate } from "@/lib/i18n";
import {
  LOCALE_BOOTSTRAP,
  LOCALE_KEY,
  locales,
  setLocale,
  supportedLocale,
} from "@/lib/i18n/locale";
import { THEME_KEY, THEME_BOOTSTRAP } from "@/lib/theme";
import {
  dateLabel,
  decimalDisplay,
  factDisplay,
  metricDisplay,
  comparisonCopy,
} from "@/lib/format";
import { MetricCards } from "@/components/dashboard/metric-card";
import { fact, playerSession } from "./fixtures";

beforeEach(() => {
  setLocale("en");
  localStorage.clear();
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  );
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
function controls() {
  return render(
    <LocaleProvider>
      <ThemeProvider>
        <LanguageControl />
        <ThemeControl />
      </ThemeProvider>
    </LocaleProvider>,
  );
}
describe("language preferences", () => {
  it("defaults to English with accessible native names and a localized title", () => {
    controls();
    expect(screen.getByRole("combobox", { name: "Language" })).toHaveValue(
      "en",
    );
    expect(screen.getByTitle("Language: English")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Português" })).toHaveValue(
      "pt-BR",
    );
    expect(screen.getByRole("option", { name: "العربية" })).toHaveValue("ar");
    expect(document.documentElement).toHaveAttribute("dir", "ltr");
  });
  it("switches language and direction immediately and restores LTR", () => {
    controls();
    fireEvent.change(screen.getByLabelText("Language"), {
      target: { value: "pt-BR" },
    });
    expect(screen.getByLabelText("Idioma")).toHaveValue("pt-BR");
    expect(screen.getByLabelText("Aparência")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Idioma"), {
      target: { value: "ar" },
    });
    expect(document.documentElement).toHaveAttribute("lang", "ar");
    expect(document.documentElement).toHaveAttribute("dir", "rtl");
    expect(screen.getByLabelText("اللغة")).toHaveValue("ar");
    fireEvent.change(screen.getByLabelText("اللغة"), {
      target: { value: "en" },
    });
    expect(document.documentElement).toHaveAttribute("dir", "ltr");
  });
  it("persists across remount and bootstrap, independent of appearance", () => {
    const view = controls();
    fireEvent.change(screen.getByLabelText("Appearance"), {
      target: { value: "dark" },
    });
    fireEvent.change(screen.getByLabelText("Language"), {
      target: { value: "ar" },
    });
    expect(localStorage.getItem(THEME_KEY)).toBe("dark");
    expect(localStorage.getItem(LOCALE_KEY)).toBe("ar");
    view.unmount();
    document.documentElement.lang = "en";
    window.eval(THEME_BOOTSTRAP + LOCALE_BOOTSTRAP);
    expect(document.documentElement).toHaveAttribute("lang", "ar");
    expect(document.documentElement.dataset.theme).toBe("dark");
    controls();
    expect(screen.getByLabelText("اللغة")).toHaveValue("ar");
    fireEvent.change(screen.getByLabelText("المظهر"), {
      target: { value: "light" },
    });
    expect(localStorage.getItem(LOCALE_KEY)).toBe("ar");
  });
  it("accepts only supported preferences before paint", () => {
    localStorage.setItem(LOCALE_KEY, "unsupported<script>");
    window.eval(LOCALE_BOOTSTRAP);
    expect(document.documentElement).toHaveAttribute("lang", "en");
    expect(supportedLocale("pt-PT")).toBe("en");
    expect(supportedLocale("constructor")).toBe("en");
  });
  it("synchronizes cross-tab changes and storage removal", () => {
    controls();
    act(() =>
      window.dispatchEvent(
        new StorageEvent("storage", { key: LOCALE_KEY, newValue: "ar" }),
      ),
    );
    expect(screen.getByLabelText("اللغة")).toHaveValue("ar");
    act(() =>
      window.dispatchEvent(
        new StorageEvent("storage", { key: LOCALE_KEY, newValue: null }),
      ),
    );
    expect(screen.getByLabelText("Language")).toHaveValue("en");
  });
  it("supports current-document selection with blocked storage", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(() => window.eval(LOCALE_BOOTSTRAP)).not.toThrow();
    const view = controls();
    fireEvent.change(screen.getByLabelText("Language"), {
      target: { value: "ar" },
    });
    view.unmount();
    controls();
    expect(screen.getByLabelText("اللغة")).toHaveValue("ar");
  });
  it("supports keyboard focus on both controls", () => {
    controls();
    screen.getByLabelText("Language").focus();
    expect(screen.getByLabelText("Language")).toHaveFocus();
    screen.getByLabelText("Appearance").focus();
    expect(screen.getByLabelText("Appearance")).toHaveFocus();
  });
});
describe("translation contracts", () => {
  it("has exact key and named-placeholder parity and no empty translations", () => {
    const placeholders = (s: string) =>
      [...new Set(s.match(/\{\w+\}/g) ?? [])].sort();
    for (const dictionary of Object.values(dictionaries)) {
      expect(Object.keys(dictionary).sort()).toEqual(
        Object.keys(dictionaries.en).sort(),
      );
      for (const [key, message] of Object.entries(dictionary)) {
        const source = dictionaries.en[key as keyof typeof dictionaries.en];
        const baseline = typeof source === "string" ? source : source.other;
        for (const text of typeof message === "string"
          ? [message]
          : Object.values(message)) {
          expect(text?.trim()).toBeTruthy();
          expect(placeholders(text!)).toEqual(placeholders(baseline));
        }
      }
    }
  });
  it("interpolates names without altering source values", () => {
    expect(
      translate("pt-BR", "Welcome back, {name}", { name: "Synthetic Player" }),
    ).toBe("Boas-vindas, Synthetic Player");
    expect(
      translate("ar", "Welcome back, {name}", { name: "Synthetic Player" }),
    ).toContain("Synthetic Player");
  });
  it.each([0, 1, 2, 3, 11, 100])(
    "uses Arabic plural rules for count %i",
    (count) => {
      const message = dictionaries.ar.sessionCount;
      expect(typeof message).toBe("object");
      const category = new Intl.PluralRules("ar").select(count);
      expect(translate("ar", "sessionCount", { count })).toBe(
        (typeof message === "string"
          ? message
          : (message[category] ?? message.other)
        ).replace("{count}", String(count)),
      );
    },
  );
  it("uses Portuguese singular and plural", () => {
    expect(translate("pt-BR", "sessionCount", { count: 1 })).toBe("1 sessão");
    expect(translate("pt-BR", "sessionCount", { count: 2 })).toBe("2 sessões");
  });
  it("localizes stable error codes and hides arbitrary error prose", () => {
    setLocale("ar");
    render(
      <LocaleProvider>
        <ErrorState
          message={
            new ApiError(
              "network_error",
              "PRIVATE INTERNAL DETAILS",
              0,
              "synthetic-request-1",
            )
          }
        />
      </LocaleProvider>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("تعذر الاتصال");
    expect(screen.getByRole("alert")).toHaveTextContent("synthetic-request-1");
    expect(screen.queryByText(/PRIVATE INTERNAL/)).not.toBeInTheDocument();
  });
  it("uses a localized fallback for unknown API errors", () => {
    setLocale("pt-BR");
    render(
      <LocaleProvider>
        <ErrorState
          message={new ApiError("future_unknown", "PRIVATE DETAILS", 500)}
        />
      </LocaleProvider>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Algo deu errado");
  });
  it("renders translated team averages and quality states", () => {
    setLocale("ar");
    render(
      <LocaleProvider>
        <TeamAverageCard
          title={translate("ar", "Average Player Load")}
          average={null}
          manager
          hasSession
        />
        <Status value="held" />
      </LocaleProvider>,
    );
    expect(screen.getByText("متوسط حمل اللاعب")).toBeInTheDocument();
    expect(screen.getByText("معلق للمراجعة")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(
      screen.getByText(translate("ar", "Reported index · same activity only")),
    ).toBeInTheDocument();
  });
});
describe("localized GPS presentation", () => {
  it.each(Object.keys(locales) as Array<keyof typeof locales>)(
    "keeps Gregorian local dates and Latin measurement digits in %s",
    (locale) => {
      const expected = new Intl.DateTimeFormat(locale, {
        calendar: "gregory",
        numberingSystem: "latn",
        month: "short",
        day: "numeric",
        year: "numeric",
        timeZone: "UTC",
      }).format(new Date("2026-02-01T12:00:00Z"));
      expect(dateLabel("2026-02-01", locale)).toBe(expected);
      expect(metricDisplay("30.4", "km/h", locale)).not.toMatch(/[٠-٩]/);
    },
  );
  it("rounds decimals losslessly beyond Number precision", () => {
    expect(decimalDisplay("9007199254740993.125", 2, "en")).toBe(
      "9,007,199,254,740,993.13",
    );
    expect(decimalDisplay("9007199254740993.125", 2, "pt-BR")).toBe(
      "9.007.199.254.740.993,13",
    );
    expect(decimalDisplay("999.995", 2, "en")).toBe("1,000");
    expect(metricDisplay("-0.01", "m", "en")).toBe("-0 m");
    expect(dateLabel("2026-02-31", "pt-BR")).toBe("2026-02-31");
    expect(factDisplay("+30.40", "pt-BR")).toBe("+30,40");
    expect(factDisplay("+source evidence", "ar")).toBe("+source evidence");
  });
  it("distinguishes missing values from printed zero", () => {
    expect(metricDisplay(null, "m", "ar")).toBe("—");
    expect(metricDisplay("0", "m", "ar")).toBe("0 m");
  });
  it("keeps workload comparison language neutral", () => {
    expect(
      comparisonCopy(
        { ...fact, percent_change: "10.25", sample_size: 5 },
        true,
        "pt-BR",
      ),
    ).toBe("+10,3% de carga vs. 5 anteriores");
  });
});

it("localizes personal metric cards while keeping workload styling neutral", () => {
  setLocale("pt-BR");
  render(
    <LocaleProvider>
      <MetricCards sessions={[playerSession]} facts={[fact]} />
    </LocaleProvider>,
  );
  expect(screen.getByText("Distância Total")).toBeInTheDocument();
  expect(screen.getByText("8.400 m")).toBeInTheDocument();
  expect(screen.getByText("+12,0% de carga vs. 5 anteriores")).not.toHaveClass(
    "positive",
  );
});
