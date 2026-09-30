import type { Metadata } from "next";
import { AuthProvider } from "@/lib/auth/provider";
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
    <html lang="en">
      <body>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
