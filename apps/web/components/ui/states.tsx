"use client";
import { useLocale } from "@/components/localization/locale-provider";
import { AlertCircle, Database, LoaderCircle } from "lucide-react";

export function Loading({ label = "Loading your data…" }: { label?: string }) {
  const { ui } = useLocale();

  return (
    <div className="card card-pad" role="status" aria-live="polite">
      <div className="flex items-center gap-3 text-sm text-muted">
        <LoaderCircle size={17} className="animate-spin" />
        {ui(label)}
      </div>
      <div className="skeleton mt-5 h-20" />
    </div>
  );
}
export function ErrorState({
  message,
  onRetry,
}: {
  message: string | Error;
  onRetry?: () => void;
}) {
  const { tr, ui } = useLocale();

  return (
    <div className="card card-pad" role="alert">
      <div className="flex items-center gap-2 font-bold text-error-text">
        <AlertCircle size={18} /> {tr("Could not load this view")}
      </div>
      <p className="page-subtitle mt-2">{ui(message)}</p>
      {onRetry && (
        <button type="button" className="btn btn-quiet mt-4" onClick={onRetry}>
          {tr("Try again")}
        </button>
      )}
    </div>
  );
}
export function EmptyState({
  title,
  children,
}: {
  title: string;
  children?: React.ReactNode;
}) {
  const { ui } = useLocale();

  return (
    <div className="empty">
      <Database size={25} className="mx-auto text-accent-text" />
      <strong>{ui(title)}</strong>
      {children}
    </div>
  );
}
