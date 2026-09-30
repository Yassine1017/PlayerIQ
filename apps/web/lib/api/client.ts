import type {
  AnalyticsFact,
  ChartReview,
  Me,
  Outliers,
  Overview,
  Page,
  Player,
  PlayerSession,
  SessionType,
  Upload,
  UploadStatus,
} from "./types";

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status: number,
    public requestId?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export const apiBase = (
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
).replace(/\/$/, "");
type TokenGetter = () => Promise<string | null>;

export class ApiClient {
  constructor(
    private token: TokenGetter,
    private onUnauthorized: () => void,
  ) {}

  async request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const accessToken = await this.token();
    if (!accessToken) {
      this.onUnauthorized();
      throw new ApiError(
        "unauthorized",
        "Your session has expired. Please sign in again.",
        401,
      );
    }
    let response: Response;
    try {
      response = await fetch(`${apiBase}${path}`, {
        ...options,
        headers: {
          Authorization: `Bearer ${accessToken}`,
          ...(options.body instanceof FormData
            ? {}
            : { "Content-Type": "application/json" }),
          ...options.headers,
        },
        cache: "no-store",
      });
    } catch {
      throw new ApiError(
        "network_error",
        "Could not reach PlayerIQ. Check your connection and try again.",
        0,
      );
    }
    if (response.status === 401) this.onUnauthorized();
    if (!response.ok) {
      const body = (await response.json().catch(() => null)) as {
        error?: { code?: string; message?: string; request_id?: string };
      } | null;
      throw new ApiError(
        body?.error?.code ?? "request_failed",
        body?.error?.message ?? `Request failed (${response.status})`,
        response.status,
        body?.error?.request_id,
      );
    }
    return response.json() as Promise<T>;
  }

  me(signal?: AbortSignal) {
    return this.request<Me>("/v1/me", { signal });
  }
  updateMe(body: { display_name?: string; timezone?: string }) {
    return this.request<Me>("/v1/me", {
      method: "PATCH",
      body: JSON.stringify(body),
    });
  }
  players(signal?: AbortSignal) {
    return this.request<{ items: Player[] }>("/v1/players", { signal });
  }
  createPlayer(display_name: string) {
    return this.request<Player>("/v1/players", {
      method: "POST",
      body: JSON.stringify({ display_name }),
    });
  }
  uploads(limit = 20, cursor?: string, signal?: AbortSignal) {
    const p = new URLSearchParams({ limit: String(limit) });
    if (cursor) p.set("cursor", cursor);
    return this.request<Page<Upload>>(`/v1/report-uploads?${p}`, { signal });
  }
  upload(id: string, signal?: AbortSignal) {
    return this.request<UploadStatus>(`/v1/report-uploads/${id}`, { signal });
  }
  chartReviews(id: string, signal?: AbortSignal) {
    return this.request<{ items: ChartReview[] }>(
      `/v1/report-uploads/${id}/chart-reviews`,
      { signal },
    );
  }
  proposeChart(
    id: string,
    source_athlete_row_id: string,
    metric_key: string,
    raw_label: string,
  ) {
    return this.request<ChartReview>(`/v1/report-uploads/${id}/chart-reviews`, {
      method: "POST",
      body: JSON.stringify({ source_athlete_row_id, metric_key, raw_label }),
    });
  }
  confirmChart(id: string, review: ChartReview, review_reason?: string) {
    return this.request<ChartReview>(
      `/v1/report-uploads/${id}/chart-reviews/${review.id}/confirm`,
      {
        method: "POST",
        body: JSON.stringify({
          source_athlete_row_id: review.source_athlete_row_id,
          raw_label: review.raw_label,
          review_reason: review_reason || null,
        }),
      },
    );
  }
  linkRow(
    id: string,
    source_athlete_row_id: string,
    player_id: string,
    session_type: SessionType,
  ) {
    return this.request<{
      session_id: string;
      player_id: string;
      source_athlete_row_id: string;
      quality_state: string;
    }>(`/v1/report-uploads/${id}/links`, {
      method: "POST",
      body: JSON.stringify({ source_athlete_row_id, player_id, session_type }),
    });
  }
  sessions(
    playerId: string,
    limit = 20,
    cursor?: string,
    signal?: AbortSignal,
  ) {
    const p = new URLSearchParams({ limit: String(limit) });
    if (cursor) p.set("cursor", cursor);
    return this.request<Page<PlayerSession>>(
      `/v1/players/${playerId}/sessions?${p}`,
      { signal },
    );
  }
  session(playerId: string, id: string, signal?: AbortSignal) {
    return this.request<PlayerSession>(
      `/v1/players/${playerId}/sessions/${id}`,
      { signal },
    );
  }
  overview(playerId: string, signal?: AbortSignal) {
    return this.request<Overview>(
      `/v1/players/${playerId}/analytics/overview`,
      { signal },
    );
  }
  trend(
    playerId: string,
    metric: string,
    from: string,
    to: string,
    type?: SessionType,
    signal?: AbortSignal,
  ) {
    const p = new URLSearchParams({ metric, from, to });
    if (type) p.set("type", type);
    return this.request<AnalyticsFact>(
      `/v1/players/${playerId}/analytics/trend?${p}`,
      { signal },
    );
  }
  outliers(
    playerId: string,
    type: "training" | "match" = "training",
    limit = 10,
    signal?: AbortSignal,
  ) {
    return this.request<Outliers>(
      `/v1/players/${playerId}/analytics/outliers?type=${type}&limit=${limit}`,
      { signal },
    );
  }
  async reportFile(id: string, signal?: AbortSignal): Promise<Blob> {
    const accessToken = await this.token();
    if (!accessToken)
      throw new ApiError("unauthorized", "Please sign in again", 401);
    const response = await fetch(`${apiBase}/v1/report-uploads/${id}/file`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      signal,
      cache: "no-store",
    });
    if (response.status === 401) this.onUnauthorized();
    if (!response.ok)
      throw new ApiError(
        "file_unavailable",
        "Private report could not be opened",
        response.status,
      );
    return response.blob();
  }
  uploadPdf(
    file: File,
    onProgress: (percent: number) => void,
  ): Promise<{ upload_id: string; status: string }> {
    return this.token().then(
      (accessToken) =>
        new Promise((resolve, reject) => {
          if (!accessToken) {
            this.onUnauthorized();
            reject(new ApiError("unauthorized", "Please sign in again", 401));
            return;
          }
          const xhr = new XMLHttpRequest();
          xhr.open("POST", `${apiBase}/v1/report-uploads`);
          xhr.setRequestHeader("Authorization", `Bearer ${accessToken}`);
          xhr.upload.onprogress = (event) => {
            if (event.lengthComputable)
              onProgress(Math.round((event.loaded / event.total) * 100));
          };
          xhr.onerror = () =>
            reject(
              new ApiError(
                "network_error",
                "Upload failed. Check your connection and retry.",
                0,
              ),
            );
          xhr.onload = () => {
            if (xhr.status === 401) this.onUnauthorized();
            let body: {
              upload_id?: string;
              status?: string;
              error?: { code?: string; message?: string };
            } = {};
            try {
              body = JSON.parse(xhr.responseText);
            } catch {
              /* server returned a non-JSON error */
            }
            if (
              xhr.status >= 200 &&
              xhr.status < 300 &&
              body.upload_id &&
              body.status
            )
              resolve({ upload_id: body.upload_id, status: body.status });
            else
              reject(
                new ApiError(
                  body.error?.code ?? "upload_failed",
                  body.error?.message ?? "Upload failed",
                  xhr.status,
                ),
              );
          };
          const form = new FormData();
          form.append("file", file);
          xhr.send(form);
        }),
    );
  }
}
