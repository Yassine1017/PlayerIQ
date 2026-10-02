import { describe, expect, it, vi } from "vitest";
import type { ApiClient } from "@/lib/api/client";
import type { UploadStatus } from "@/lib/api/types";
import {
  canClaimReport,
  canSelectSelf,
  loadIdentityReports,
} from "@/lib/data/use-identity-reports";
import { row } from "./fixtures";

const report: UploadStatus = {
  upload_id: "u1",
  status: "awaiting_link",
  error_code: null,
  findings: [],
  candidate_rows: [row],
  activity: {
    source_title: "Synthetic report",
    source_team_name: null,
    source_venue_name: null,
    reported_local_datetime: "2026-02-01",
    timezone: null,
    activity_total_time_s: null,
  },
};
describe("safe report choices", () => {
  it("requires ready rows and rejects another player's existing link", () => {
    expect(
      canSelectSelf({ ...row, quality_state: "zero_recorded" }, "p1"),
    ).toBe(false);
    expect(canSelectSelf({ ...row, quality_state: "needs_review" }, "p1")).toBe(
      false,
    );
    expect(
      canSelectSelf(
        {
          ...row,
          links: [
            { player_id: "p2", session_id: "s1", quality_state: "accepted" },
          ],
        },
        "p1",
      ),
    ).toBe(false);
    expect(canClaimReport({ ...report, activity: null }, "p1", [])).toBe(false);
    expect(canClaimReport(report, "p1", [])).toBe(true);
  });
  it("does not offer assigned team reports without manager and owned-player membership", () => {
    const team = {
      id: "t1",
      name: "Synthetic FC",
      role: "player" as const,
      player_id: "p1",
      created_at: "2026-01-01",
    };
    expect(canClaimReport({ ...report, team_id: "t1" }, "p1", [team])).toBe(
      false,
    );
    expect(
      canClaimReport({ ...report, team_id: "t1" }, "p1", [
        { ...team, role: "coach", player_id: null },
      ]),
    ).toBe(false);
    expect(
      canClaimReport({ ...report, team_id: "t1" }, "p1", [
        { ...team, role: "admin" },
      ]),
    ).toBe(true);
  });
  it("preserves pagination uncertainty and reads only processed uploader reports", async () => {
    const api = {
      uploads: vi.fn().mockResolvedValue({
        items: [
          { upload_id: "u1", status: "awaiting_link" },
          { upload_id: "queued", status: "queued" },
        ],
        next_cursor: "older",
      }),
      teams: vi.fn().mockResolvedValue({ items: [] }),
      upload: vi.fn().mockResolvedValue(report),
    };
    const result = await loadIdentityReports(
      api as unknown as ApiClient,
      "p1",
      1,
      new AbortController().signal,
    );
    expect(result.nextCursor).toBe("older");
    expect(result.eligible).toHaveLength(1);
    expect(api.upload).toHaveBeenCalledTimes(1);
    expect(api.upload).toHaveBeenCalledWith("u1", expect.any(AbortSignal));
  });
  it("fails closed when a processed report cannot be inspected", async () => {
    const api = {
      uploads: vi.fn().mockResolvedValue({
        items: [{ upload_id: "u1", status: "awaiting_link" }],
        next_cursor: null,
      }),
      teams: vi.fn().mockResolvedValue({ items: [] }),
      upload: vi.fn().mockRejectedValue(new Error("Report unavailable")),
    };
    await expect(
      loadIdentityReports(
        api as unknown as ApiClient,
        "p1",
        1,
        new AbortController().signal,
      ),
    ).rejects.toThrow("Report unavailable");
  });
  it("includes older eligible reports before concluding the choice is unique", async () => {
    const api = {
      uploads: vi
        .fn()
        .mockResolvedValueOnce({
          items: [{ upload_id: "u1", status: "awaiting_link" }],
          next_cursor: "older",
        })
        .mockResolvedValueOnce({
          items: [{ upload_id: "u2", status: "awaiting_link" }],
          next_cursor: null,
        }),
      teams: vi.fn().mockResolvedValue({ items: [] }),
      upload: vi.fn().mockImplementation(async (id: string) => ({
        ...report,
        upload_id: id,
      })),
    };
    const result = await loadIdentityReports(
      api as unknown as ApiClient,
      "p1",
      2,
      new AbortController().signal,
    );
    expect(result.eligible.map((item) => item.upload.upload_id)).toEqual([
      "u1",
      "u2",
    ]);
    expect(result.nextCursor).toBeNull();
    expect(api.uploads).toHaveBeenLastCalledWith(
      50,
      "older",
      expect.any(AbortSignal),
    );
  });
});
