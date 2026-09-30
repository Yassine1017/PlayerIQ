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
});
