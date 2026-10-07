import type { Metadata } from "next";
import { AuthProvider } from "@/lib/auth/provider";
import { ThemeProvider } from "@/components/theme/theme-provider";
import { THEME_BOOTSTRAP } from "@/lib/theme";
import "./globals.css";
import { LocaleProvider } from "@/components/localization/locale-provider";
import { LOCALE_BOOTSTRAP } from "@/lib/i18n/locale";

export const metadata: Metadata = {
  title: "PlayerIQ | Football performance, in focus",
  description:
    "Understand your football GPS sessions with reviewed data and grounded performance analytics.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" dir="ltr" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: THEME_BOOTSTRAP + LOCALE_BOOTSTRAP,
          }}
        />
      </head>
      <body>
        <ThemeProvider>
          <LocaleProvider>
            <AuthProvider>{children}</AuthProvider>
          </LocaleProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
