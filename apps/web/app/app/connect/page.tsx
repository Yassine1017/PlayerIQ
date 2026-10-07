"use client";
import { useLocale } from "@/components/localization/locale-provider";

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
  const { tr, locale } = useLocale();

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
          <span className="eyebrow">{tr("Connect your player identity")}</span>
          <h1 className="page-title">{tr("Choose a GPS report")}</h1>
          <p className="page-subtitle">
            {tr(
              "Choose the report you want to use, then select yourself from its athlete rows.",
            )}
          </p>
        </div>
      </div>
      {reports.loading || direct ? (
        <Loading label={tr("Finding your report…")} />
      ) : reports.error ? (
        <ErrorState message={reports.error} onRetry={reports.refresh} />
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
                      {dateLabel(
                        report.activity?.reported_local_datetime,
                        locale,
                      )}{" "}
                      ·{" "}
                      {tr("athleteCount", {
                        count: report.candidate_rows.length,
                      })}
                    </p>
                    <Link
                      className="btn btn-primary mt-4"
                      href={identityReportHref(upload.upload_id)}
                    >
                      {tr("Choose this report →")}
                    </Link>
                  </section>
                ))}
              </div>
            ) : (
              <EmptyState
                title={
                  reports.data.nextCursor
                    ? tr("No suitable report in loaded history")
                    : tr("No suitable processed report yet")
                }
              >
                {reports.data.nextCursor
                  ? tr("Load older reports to check the rest of your history.")
                  : tr(
                      "Upload a GPS report, or wait for processing to finish.",
                    )}
                {tr(
                  "A report needs an eligible athlete row before it can create an accepted session.",
                )}
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
                    <bdi dir="auto">{upload.original_filename}</bdi>
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
                  {tr("Load older reports")}
                </button>
              )}
              {reports.data.nextCursor && reports.atLimit && (
                <Link href="/app/upload" className="btn btn-quiet">
                  {tr("Browse older reports in My Reports")}
                </Link>
              )}
              <button
                type="button"
                className="btn btn-quiet"
                onClick={reports.refresh}
              >
                {tr("Refresh reports")}
              </button>
              <Link href="/app/upload" className="btn btn-primary">
                {tr("Upload a GPS report")}
              </Link>
            </div>
          </>
        )
      )}
    </div>
  );
}
