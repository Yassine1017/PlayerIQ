"use client";

import { ArrowRight, Check, Fingerprint } from "lucide-react";
import Link from "next/link";
import { useApp } from "@/components/layout/app-frame";
import { ErrorState, Loading } from "@/components/ui/states";
import { useAuth } from "@/lib/auth/provider";
import {
  identityReportHref,
  processingReportStates,
  useIdentityReports,
} from "@/lib/data/use-identity-reports";
import { statusText } from "@/lib/format";

export function IdentitySteps({
  uploaded,
  selected = false,
}: {
  uploaded: boolean;
  selected?: boolean;
}) {
  return (
    <ol className="identity-steps" aria-label="Player identity progress">
      {[
        { label: "GPS report uploaded", done: uploaded },
        { label: "Select yourself from the report", done: selected },
        { label: "Confirm your player identity", done: false },
      ].map((step, index) => (
        <li key={step.label} className={step.done ? "complete" : ""}>
          <span className="identity-step-number" aria-hidden="true">
            {step.done ? <Check size={15} /> : index + 1}
          </span>
          <span>
            {step.label}
            <span className="sr-only">
              {" "}
              — {step.done ? "complete" : "pending"}
            </span>
          </span>
        </li>
      ))}
    </ol>
  );
}

export function IdentityOnboarding() {
  const { api } = useAuth();
  const { player } = useApp();
  const reports = useIdentityReports(api, player.id);
  const options = reports.data;
  const processing =
    options?.uploads.filter((item) =>
      processingReportStates.has(item.status),
    ) ?? [];
  const hasChoice = Boolean(options?.eligible.length || options?.nextCursor);
  const direct = options?.eligible.length === 1 && !options.nextCursor;
  return (
    <section
      className="identity-onboarding"
      aria-labelledby="connect-player-heading"
    >
      <div className="identity-onboarding-head">
        <span className="identity-symbol" aria-hidden="true">
          <Fingerprint size={25} />
        </span>
        <div>
          <span className="eyebrow">Your first step</span>
          <h2 id="connect-player-heading">Connect your player identity</h2>
          <p>
            Select yourself from an uploaded GPS report to unlock your personal
            performance dashboard. You only need to confirm your identity once.
          </p>
        </div>
      </div>
      <IdentitySteps uploaded={Boolean(options?.uploads.length)} />
      {reports.loading ? (
        <Loading label="Checking your GPS reports…" />
      ) : reports.error ? (
        <ErrorState message={reports.error.message} onRetry={reports.refresh} />
      ) : (
        processing.length > 0 && (
          <p className="identity-progress-note" role="status">
            {processing.length === 1
              ? "Your report is"
              : `${processing.length} reports are`}{" "}
            still processing:{" "}
            {processing.map((item) => statusText(item.status)).join(", ")}.
            Refresh when processing finishes.
          </p>
        )
      )}
      <div className="identity-actions">
        {!reports.loading && (
          <Link
            className="btn btn-primary"
            href={
              reports.error
                ? "/app/connect"
                : hasChoice
                  ? direct
                    ? identityReportHref(options!.eligible[0].upload.upload_id)
                    : "/app/connect"
                  : "/app/upload"
            }
          >
            {hasChoice || reports.error
              ? "Choose my player identity"
              : "Upload a GPS report"}
            <ArrowRight size={16} />
          </Link>
        )}
        {processing.length > 0 && (
          <button
            type="button"
            className="inline-link"
            onClick={reports.refresh}
          >
            Refresh report status
          </button>
        )}
      </div>
    </section>
  );
}
