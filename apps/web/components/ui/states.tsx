import { AlertCircle, Database, LoaderCircle } from "lucide-react";

export function Loading({ label = "Loading your data…" }: { label?: string }) {
  return (
    <div className="card card-pad" role="status" aria-live="polite">
      <div className="flex items-center gap-3 text-sm text-slate-500">
        <LoaderCircle size={17} className="animate-spin" />
        {label}
      </div>
      <div className="skeleton mt-5 h-20" />
    </div>
  );
}
export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="card card-pad" role="alert">
      <div className="flex items-center gap-2 font-bold text-rose-700">
        <AlertCircle size={18} /> Could not load this view
      </div>
      <p className="page-subtitle mt-2">{message}</p>
      {onRetry && (
        <button type="button" className="btn btn-quiet mt-4" onClick={onRetry}>
          Try again
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
  return (
    <div className="empty">
      <Database size={25} className="mx-auto text-emerald-600" />
      <strong>{title}</strong>
      {children}
    </div>
  );
}
