"use client";

import { useCallback, useState } from "react";
import type { ApiClient } from "@/lib/api/client";
import type { CandidateRow, Team, Upload, UploadStatus } from "@/lib/api/types";
import { useResource } from "./use-resource";

export const processingReportStates = new Set([
  "received",
  "queued",
  "extracting",
  "validating",
  "failed_retryable",
]);

export function canSelectSelf(row: CandidateRow, playerId: string) {
  return (
    row.quality_state === "ready" &&
    row.links.every(
      (link) =>
        (link.player_id === playerId || link.is_unclaimed === true) &&
        link.quality_state === "accepted",
    )
  );
}

export function canClaimReport(
  report: UploadStatus,
  playerId: string,
  teams: Team[],
) {
  const team = teams.find((item) => item.id === report.team_id);
  const allowedScope =
    !report.team_id ||
    (team?.role !== "player" && team?.player_id === playerId);
  return Boolean(
    allowedScope &&
    report.status === "awaiting_link" &&
    report.activity?.reported_local_datetime &&
    report.candidate_rows.some((row) => canSelectSelf(row, playerId)),
  );
}

export interface IdentityReportChoice {
  upload: Upload;
  report: UploadStatus;
}
export interface IdentityReports {
  eligible: IdentityReportChoice[];
  uploads: Upload[];
  nextCursor: string | null;
}

// Read only uploader-authorized API results. An unfinished page never proves
// that the visible report is the only suitable report in the account history.
export async function loadIdentityReports(
  api: ApiClient,
  playerId: string,
  pageCount: number,
  signal: AbortSignal,
): Promise<IdentityReports> {
  const [first, membership] = await Promise.all([
    api.uploads(50, undefined, signal),
    api.teams(signal),
  ]);
  const uploads: Upload[] = [...first.items];
  let cursor = first.next_cursor ?? undefined;
  for (let page = 1; page < pageCount && cursor; page++) {
    const result = await api.uploads(50, cursor, signal);
    uploads.push(...result.items);
    if (!result.next_cursor) {
      cursor = undefined;
      break;
    }
    if (result.next_cursor === cursor)
      throw new Error("Report history could not be loaded completely");
    cursor = result.next_cursor;
  }
  const ready = uploads.filter((item) => item.status === "awaiting_link");
  const reports: IdentityReportChoice[] = [];
  // Bound detail requests even when the uploader loads several history pages.
  for (let offset = 0; offset < ready.length; offset += 5) {
    const batch = await Promise.all(
      ready.slice(offset, offset + 5).map(async (upload) => ({
        upload,
        report: await api.upload(upload.upload_id, signal),
      })),
    );
    reports.push(...batch);
  }
  return {
    uploads,
    eligible: reports.filter(({ report }) =>
      canClaimReport(report, playerId, membership.items),
    ),
    nextCursor: cursor ?? null,
  };
}

export function useIdentityReports(api: ApiClient, playerId: string) {
  const [pageCount, setPageCount] = useState(1);
  const load = useCallback(
    (signal: AbortSignal) =>
      loadIdentityReports(api, playerId, pageCount, signal),
    [api, playerId, pageCount],
  );
  const resource = useResource(
    `identity-reports:${playerId}:${pageCount}`,
    load,
  );
  return {
    ...resource,
    loadMore: () => setPageCount((count) => Math.min(count + 1, 20)),
    atLimit: pageCount === 20,
  };
}

export function identityReportHref(id: string) {
  return `/app/uploads/${encodeURIComponent(id)}#player-identity`;
}
