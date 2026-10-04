import type { Metadata } from "next";
import { AuthProvider } from "@/lib/auth/provider";
import { ThemeProvider } from "@/components/theme/theme-provider";
import { THEME_BOOTSTRAP } from "@/lib/theme";
import "./globals.css";

export const metadata: Metadata = {
  title: "PlayerIQ | Football performance, in focus",
  description:
    "Understand your football GPS sessions with reviewed data and grounded performance analytics.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOTSTRAP }} />
      </head>
      <body>
        <ThemeProvider>
          <AuthProvider>{children}</AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
