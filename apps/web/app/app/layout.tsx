import { AppFrame } from "@/components/layout/app-frame";

export default function ApplicationLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <AppFrame>{children}</AppFrame>;
}
