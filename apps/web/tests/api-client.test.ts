import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiClient, ApiError } from "@/lib/api/client";

afterEach(() => vi.unstubAllGlobals());
describe("authenticated API client", () => {
  it("attaches the current access token and parses a typed response", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ items: [] }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetcher);
    const api = new ApiClient(async () => "synthetic-token", vi.fn());
    expect((await api.players()).items).toEqual([]);
    expect(fetcher.mock.calls[0][1].headers.Authorization).toBe(
      "Bearer synthetic-token",
    );
  });
  it("handles an expired token and API 401", async () => {
    const unauthorized = vi.fn();
    const missing = new ApiClient(async () => null, unauthorized);
    await expect(missing.me()).rejects.toMatchObject({
      code: "unauthorized",
      status: 401,
    });
    expect(unauthorized).toHaveBeenCalledTimes(1);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: {
              code: "invalid_token",
              message: "Expired",
              request_id: "request-1",
            },
          }),
          { status: 401 },
        ),
      ),
    );
    const api = new ApiClient(async () => "expired-token", unauthorized);
    await expect(api.me()).rejects.toMatchObject({
      code: "invalid_token",
      status: 401,
      requestId: "request-1",
    });
    expect(unauthorized).toHaveBeenCalledTimes(2);
  });
  it("reports inaccessible resources as 404 without exposing data", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: { code: "not_found", message: "Not found" },
          }),
          { status: 404 },
        ),
      ),
    );
    const api = new ApiClient(async () => "synthetic-token", vi.fn());
    await expect(api.upload("another-account-upload")).rejects.toMatchObject({
      status: 404,
    });
  });
  it("uses a stable network error for fetch failures", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    const api = new ApiClient(async () => "synthetic-token", vi.fn());
    await expect(api.me()).rejects.toBeInstanceOf(ApiError);
    await expect(api.me()).rejects.toMatchObject({ code: "network_error" });
  });
  it("reports an upload HTTP failure without exposing backend details", async () => {
    class FailedUploadRequest {
      upload = { onprogress: null };
      status = 503;
      responseText = JSON.stringify({
        error: {
          code: "upload_processing_failed",
          message: "internal table details",
          request_id: "synthetic-request",
        },
      });
      onload: (() => void) | null = null;
      open() {}
      setRequestHeader() {}
      send() {
        this.onload?.();
      }
    }
    vi.stubGlobal("XMLHttpRequest", FailedUploadRequest);
    const api = new ApiClient(async () => "synthetic-token", vi.fn());
    await expect(
      api.uploadPdf(new File(["%PDF"], "synthetic.pdf"), vi.fn()),
    ).rejects.toMatchObject({
      code: "upload_processing_failed",
      status: 503,
      requestId: "synthetic-request",
      message: "We couldn't process this report. Please try again.",
    });
  });
  it("keeps an unreachable upload API distinct from an HTTP failure", async () => {
    class UnreachableUploadRequest {
      upload = { onprogress: null };
      onerror: (() => void) | null = null;
      open() {}
      setRequestHeader() {}
      send() {
        this.onerror?.();
      }
    }
    vi.stubGlobal("XMLHttpRequest", UnreachableUploadRequest);
    const api = new ApiClient(async () => "synthetic-token", vi.fn());
    await expect(
      api.uploadPdf(new File(["%PDF"], "synthetic.pdf"), vi.fn()),
    ).rejects.toMatchObject({ code: "network_error", status: 0 });
  });
});
