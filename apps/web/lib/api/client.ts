import type {
  AnalyticsFact,
  AnalystResponse,
  ChatMessage,
  ChatThread,
  ChartReview,
  Me,
  Outliers,
  Overview,
  Page,
  Player,
  PlayerSession,
  SessionType,
  SourceIdentity,
  Team,
  TeamJoinRequest,
  TeamPlayer,
  TeamParticipant,
  TeamSession,
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
  sourceIdentities(signal?: AbortSignal) {
    return this.request<{ items: SourceIdentity[] }>(
      "/v1/me/source-identities",
      { signal },
    );
  }
  revokeSourceIdentity(id: string) {
    return this.request<SourceIdentity>(
      `/v1/me/source-identities/${id}/revoke`,
      {
        method: "POST",
        body: JSON.stringify({ confirm: true }),
      },
    );
  }
  claimSelf(
    uploadId: string,
    body: {
      source_athlete_row_id: string;
      player_id: string;
      confirmed_source_label: string;
      session_type: SessionType;
    },
  ) {
    return this.request<{ session_id: string; identity: SourceIdentity }>(
      `/v1/report-uploads/${uploadId}/claim-as-self`,
      { method: "POST", body: JSON.stringify(body) },
    );
  }
  confirmTeamPlayer(
    uploadId: string,
    body: {
      source_athlete_row_id: string;
      player_id: string;
      confirmed_source_label: string;
      session_type: SessionType;
    },
  ) {
    return this.request<{ session_id: string; identity: SourceIdentity }>(
      `/v1/report-uploads/${uploadId}/confirm-team-player`,
      { method: "POST", body: JSON.stringify(body) },
    );
  }
  teams(signal?: AbortSignal) {
    return this.request<{ items: Team[] }>("/v1/teams", { signal });
  }
  createTeam(name: string) {
    return this.request<Team>("/v1/teams", {
      method: "POST",
      body: JSON.stringify({ name }),
    });
  }
  requestTeamJoin(teamId: string) {
    return this.request<TeamJoinRequest>(`/v1/teams/${teamId}/join-requests`, {
      method: "POST",
      body: "{}",
    });
  }
  teamJoinRequests(teamId: string, signal?: AbortSignal) {
    return this.request<{ items: TeamJoinRequest[] }>(
      `/v1/teams/${teamId}/join-requests`,
      { signal },
    );
  }
  approveTeamJoin(teamId: string, requestId: string, role: "player" | "coach") {
    return this.request<Team>(
      `/v1/teams/${teamId}/join-requests/${requestId}/approve`,
      { method: "POST", body: JSON.stringify({ role }) },
    );
  }
  assignReportTeam(uploadId: string, teamId: string) {
    return this.request<Team>(`/v1/report-uploads/${uploadId}/team`, {
      method: "POST",
      body: JSON.stringify({ team_id: teamId, confirm_share: true }),
    });
  }
  teamDashboard(teamId: string, signal?: AbortSignal) {
    return this.request<{
      team: Team;
      latest_session: TeamSession | null;
      recent_sessions: TeamSession[];
      player_count: number | null;
      rule_version: string;
    }>(`/v1/teams/${teamId}/dashboard`, { signal });
  }
  teamSessions(teamId: string, signal?: AbortSignal) {
    return this.request<{ items: TeamSession[] }>(
      `/v1/teams/${teamId}/sessions`,
      { signal },
    );
  }
  teamSession(teamId: string, reportId: string, signal?: AbortSignal) {
    return this.request<{
      summary: TeamSession;
      participants: TeamParticipant[];
    }>(`/v1/teams/${teamId}/sessions/${reportId}`, { signal });
  }
  teamPlayers(teamId: string, signal?: AbortSignal) {
    return this.request<{ items: TeamPlayer[]; limited_to_self: boolean }>(
      `/v1/teams/${teamId}/players`,
      { signal },
    );
  }
  teamPlayerOverview(teamId: string, playerId: string, signal?: AbortSignal) {
    return this.request<Overview>(`/v1/teams/${teamId}/players/${playerId}`, {
      signal,
    });
  }
  teamReports(teamId: string, signal?: AbortSignal) {
    return this.request<{
      items: {
        upload_id: string;
        status: string;
        created_at: string;
        accepted_player_count: number;
      }[];
    }>(`/v1/teams/${teamId}/reports`, { signal });
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
    source_identity_id?: string,
  ) {
    return this.request<{
      session_id: string;
      player_id: string;
      source_athlete_row_id: string;
      quality_state: string;
    }>(`/v1/report-uploads/${id}/links`, {
      method: "POST",
      body: JSON.stringify({
        source_athlete_row_id,
        player_id,
        session_type,
        source_identity_id,
      }),
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
  chats(playerId: string, cursor?: string, signal?: AbortSignal) {
    const params = new URLSearchParams({ limit: "20" });
    if (cursor) params.set("cursor", cursor);
    return this.request<Page<ChatThread>>(
      `/v1/players/${playerId}/chats?${params}`,
      { signal },
    );
  }
  createChat(playerId: string, title?: string) {
    return this.request<ChatThread>(`/v1/players/${playerId}/chats`, {
      method: "POST",
      body: JSON.stringify({ title: title || null }),
    });
  }
  chatMessages(playerId: string, threadId: string, cursor?: string) {
    const params = new URLSearchParams({ limit: "30" });
    if (cursor) params.set("cursor", cursor);
    return this.request<Page<ChatMessage>>(
      `/v1/players/${playerId}/chats/${threadId}/messages?${params}`,
    );
  }
  askAnalyst(
    playerId: string,
    threadId: string,
    question: string,
    requestId: string,
  ) {
    return this.request<AnalystResponse>(
      `/v1/players/${playerId}/chats/${threadId}/messages`,
      {
        method: "POST",
        body: JSON.stringify({ question, request_id: requestId }),
      },
    );
  }
  sessionAnalysis(playerId: string, sessionId: string) {
    return this.request<AnalystResponse>(
      `/v1/players/${playerId}/sessions/${sessionId}/analysis`,
    );
  }
  analyzeSession(playerId: string, sessionId: string, requestId: string) {
    return this.request<AnalystResponse>(
      `/v1/players/${playerId}/sessions/${sessionId}/analysis`,
      { method: "POST", body: JSON.stringify({ request_id: requestId }) },
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
    teamId?: string,
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
              error?: { code?: string; message?: string; request_id?: string };
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
            else if (xhr.status >= 500)
              reject(
                new ApiError(
                  "upload_processing_failed",
                  "We couldn't process this report. Please try again.",
                  xhr.status,
                  body.error?.request_id,
                ),
              );
            else
              reject(
                new ApiError(
                  body.error?.code ?? "upload_failed",
                  body.error?.message ?? "Upload failed",
                  xhr.status,
                  body.error?.request_id,
                ),
              );
          };
          const form = new FormData();
          form.append("file", file);
          if (teamId) form.append("team_id", teamId);
          xhr.send(form);
        }),
    );
  }
}
