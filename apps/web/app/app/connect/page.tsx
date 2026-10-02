"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useApp } from "@/components/layout/app-frame";
import { EmptyState, ErrorState, Loading } from "@/components/ui/states";
import { Status } from "@/components/ui/status";
import { useAuth } from "@/lib/auth/provider";
import {
  identityReportHref,
  processingReportStates,
  useIdentityReports,
} from "@/lib/data/use-identity-reports";
import { dateLabel } from "@/lib/format";

export default function ConnectIdentityPage() {
  const { api } = useAuth();
  const { player } = useApp();
  const router = useRouter();
  const reports = useIdentityReports(api, player.id);
  const direct =
    !reports.loading &&
    !reports.error &&
    reports.data?.eligible.length === 1 &&
    !reports.data.nextCursor;
  const onlyReportId = direct
    ? reports.data?.eligible[0].upload.upload_id
    : undefined;
  useEffect(() => {
    if (onlyReportId) router.replace(identityReportHref(onlyReportId));
  }, [onlyReportId, router]);
  return (
    <div className="stack">
      <div className="page-heading">
        <div>
          <span className="eyebrow">Connect your player identity</span>
          <h1 className="page-title">Choose a GPS report</h1>
          <p className="page-subtitle">
            Choose the report you want to use, then select yourself from its
            athlete rows.
          </p>
        </div>
      </div>
      {reports.loading || direct ? (
        <Loading label="Finding your report…" />
      ) : reports.error ? (
        <ErrorState message={reports.error.message} onRetry={reports.refresh} />
      ) : (
        reports.data && (
          <>
            {reports.data.eligible.length ? (
              <div className="grid gap-3 md:grid-cols-2">
                {reports.data.eligible.map(({ upload, report }) => (
                  <section
                    className="card card-pad min-w-0"
                    key={upload.upload_id}
                  >
                    <h2 className="section-title break-words">
                      {report.activity?.source_title ??
                        upload.original_filename}
                    </h2>
                    <p className="helper mt-2">
                      {dateLabel(report.activity?.reported_local_datetime)} ·{" "}
                      {report.candidate_rows.length} source athletes
                    </p>
                    <Link
                      className="btn btn-primary mt-4"
                      href={identityReportHref(upload.upload_id)}
                    >
                      Choose this report →
                    </Link>
                  </section>
                ))}
              </div>
            ) : (
              <EmptyState
                title={
                  reports.data.nextCursor
                    ? "No suitable report in loaded history"
                    : "No suitable processed report yet"
                }
              >
                {reports.data.nextCursor
                  ? "Load older reports to check the rest of your history. "
                  : "Upload a GPS report, or wait for processing to finish. "}
                A report needs an eligible athlete row before it can create an
                accepted session.
              </EmptyState>
            )}
            {reports.data.uploads
              .filter((item) => processingReportStates.has(item.status))
              .map((upload) => (
                <div
                  className="card card-pad flex flex-wrap gap-3 items-center justify-between"
                  key={upload.upload_id}
                >
                  <span className="text-sm font-semibold break-words">
                    {upload.original_filename}
                  </span>
                  <Status value={upload.status} />
                </div>
              ))}
            <div className="flex flex-wrap gap-3">
              {reports.data.nextCursor && !reports.atLimit && (
                <button
                  type="button"
                  className="btn btn-quiet"
                  onClick={reports.loadMore}
                >
                  Load older reports
                </button>
              )}
              {reports.data.nextCursor && reports.atLimit && (
                <Link href="/app/upload" className="btn btn-quiet">
                  Browse older reports in My Reports
                </Link>
              )}
              <button
                type="button"
                className="btn btn-quiet"
                onClick={reports.refresh}
              >
                Refresh reports
              </button>
              <Link href="/app/upload" className="btn btn-primary">
                Upload a GPS report
              </Link>
            </div>
          </>
        )
      )}
    </div>
  );
}
