/** Maintained against FastAPI /openapi.json (schemas.v1 and schemas.analytics). */
export type QualityStatus =
  | "accepted"
  | "ready"
  | "needs_review"
  | "zero_recorded"
  | "held"
  | "missing"
  | "proposed"
  | "confirmed"
  | "superseded"
  | string;
export type SessionType = "training" | "match" | "unknown";

export interface Profile {
  display_name: string;
  timezone: string;
}
export interface Me {
  user_id: string;
  profile: Profile | null;
}
export interface Player {
  id: string;
  display_name: string;
  owner_user_id: string;
  created_at: string;
}
export interface Finding {
  code: string;
  message: string;
  severity: string;
  scope: string;
  row_ordinal: number | null;
  metric_key: string | null;
}
export interface SourceMetric {
  source_label: string;
  raw_value: string | null;
  raw_unit: string | null;
  parsed_value: string | null;
  quality_state: string;
  source_locator: string | null;
}
export interface CandidateRow {
  id: string;
  row_ordinal: number;
  source_name: string;
  source_position_code: string | null;
  quality_state: string;
  metrics: SourceMetric[];
  missing_metrics: string[];
  findings: Finding[];
  links: { session_id: string; player_id: string; quality_state: string }[];
}
export interface Activity {
  source_title: string;
  source_team_name: string | null;
  source_venue_name: string | null;
  reported_local_datetime: string | null;
  timezone: string | null;
  activity_total_time_s: number | null;
}
export interface Upload {
  upload_id: string;
  original_filename: string;
  status: string;
  created_at: string;
  processed_at: string | null;
  athlete_row_count: number | null;
  error_code: string | null;
}
export interface UploadStatus {
  upload_id: string;
  status: string;
  error_code: string | null;
  activity: Activity | null;
  findings: Finding[];
  candidate_rows: CandidateRow[];
}
export interface ChartReview {
  id: string;
  source_athlete_row_id: string;
  metric_key: string;
  raw_label: string;
  parsed_value: string;
  unit: string;
  source_locator: string;
  capture_method: string;
  status: string;
  proposed_by_user_id: string;
  reviewed_by_user_id: string | null;
  reviewed_at: string | null;
  review_reason: string | null;
  source_observation_id: string | null;
  created_at: string;
}
export interface SessionMetric {
  metric_key: string;
  value: string;
  unit: string;
  source_label: string;
  definition_id: string | null;
  comparability_key: string;
  quality_state: string;
}
export interface PlayerSession {
  id: string;
  player_id: string;
  local_date: string;
  session_type: SessionType;
  quality_state: string;
  metrics: SessionMetric[];
  warnings: Finding[];
  provenance: { source_athlete_row_id: string; report_upload_id: string };
}
export interface TrendPoint {
  session_id: string;
  local_date: string;
  session_type: SessionType;
  value: string;
  source_observation_id: string;
}
export interface SupportingMetric {
  metric_key: string;
  value: string;
  display_value: string;
  unit: string;
  source_observation_id: string;
  definition_id: string | null;
  comparability_key: string;
}
export interface AnalyticsFact {
  kind: string;
  status: string;
  rule_version: string;
  metric_key: string | null;
  value: string | null;
  display_value: string | null;
  unit: string | null;
  baseline_value: string | null;
  delta: string | null;
  percent_change: string | null;
  slope_per_week: string | null;
  median_value: string | null;
  mad: string | null;
  score: string | null;
  sample_size: number;
  session_ids: string[];
  source_observation_ids: string[];
  points: TrendPoint[];
  supporting_metrics: SupportingMetric[];
  from_date: string | null;
  to_date: string | null;
  definition_id: string | null;
  comparability_key: string | null;
  note: string | null;
}
export interface Overview {
  player_id: string;
  history_fingerprint: string;
  rule_version: string;
  facts: AnalyticsFact[];
}
export interface Outliers {
  history_fingerprint: string;
  rule_version: string;
  items: AnalyticsFact[];
}
export interface Page<T> {
  items: T[];
  next_cursor: string | null;
}

export interface AnalystFact {
  fact_id: string;
  kind: string;
  metric_key: string | null;
  role: string;
  raw_value: string;
  display_value: string;
  unit: string;
  rule_version: string;
  status: string;
  sample_size: number;
  source_session_ids: string[];
  source_observation_ids: string[];
  definition_id: string | null;
  comparability_key: string | null;
}
export interface AnalystAnswer {
  status: "answered" | "insufficient_data" | "unavailable";
  sentences: { text: string; fact_ids: string[]; session_ids: string[] }[];
}
export interface AnalystResponse {
  run_id: string;
  player_id: string;
  thread_id: string | null;
  session_id: string | null;
  answer: AnalystAnswer;
  facts: AnalystFact[];
  results: {
    tool: string;
    items: {
      kind: string;
      status: string;
      metric_key: string | null;
      fact_ids: string[];
      session_ids: string[];
      source_observation_ids: string[];
      source_ids_truncated: boolean;
      from_date: string | null;
      to_date: string | null;
      note: string | null;
      rule_version: string;
    }[];
  }[];
  generated_at: string | null;
  model: string;
  provider: string;
  prompt_version: string;
  analytics_rule_version: string;
  history_fingerprint: string;
  stale: boolean;
  error_code?: string | null;
}
export interface ChatThread {
  id: string;
  player_id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}
export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  question: string | null;
  analysis: AnalystResponse | null;
  created_at: string;
}

export const metricLabels: Record<string, string> = {
  total_distance_m: "Total Distance",
  reported_high_speed_distance_m: "High-Speed Distance",
  maximum_velocity_kmh: "Maximum Velocity",
  player_load_reported: "Player Load",
  reported_meterage_per_minute: "Meterage per Minute",
  reported_accel_decel_efforts_combined: "Acceleration + Deceleration Efforts",
  reported_accel_decel_efforts_per_min: "Efforts per Minute",
  reported_sprint_efforts: "Sprint Efforts",
  velocity_band_2_distance_m: "Velocity Band 2 Distance",
  velocity_band_4_distance_m: "Velocity Band 4 Distance",
};

export const trendMetrics = [
  "total_distance_m",
  "reported_high_speed_distance_m",
  "maximum_velocity_kmh",
  "player_load_reported",
] as const;
