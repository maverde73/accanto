/** Contracts mirrored from the backend (see backend/app/schemas). */

export type HeadlineState = "active" | "moving" | "vitals_only" | "quiet" | "no_data";
export type Tone = "green" | "amber" | "grey" | "red";

export interface Headline {
  state: HeadlineState;
  color: string;
  at: string | null;
  evidence_kind: string | null;
  evidence: string | null;
}

export interface Clocks {
  interaction: string | null;
  movement: string | null;
  vital: string | null;
  contact: string | null;
}

export interface Snapshot {
  subject_id: string;
  computed_at: string;
  headline: Headline;
  clocks: Clocks;
  vitals: { bpm: number | null; bpm_at: string | null };
  batteries: { phone_pct: number | null; watch_likely_charging: boolean };
  pipeline: { lag_seconds_p90: number | null; healthy: boolean };
}

export interface SubjectSummary {
  id: string;
  display_name: string;
  timezone: string;
  scopes: string[];
}

export interface LocationPoint {
  lat: number;
  lon: number;
  accuracy_m: number | null;
  speed_mps?: number | null;
  battery_pct?: number | null;
  at: string;
  precision: "precise" | "coarse";
}

export interface Alert {
  id: string;
  severity: "amber" | "red";
  title: string;
  detail: Record<string, unknown>;
  occurred_at: string;
  acknowledged_at: string | null;
}

export interface Checkin {
  id: string;
  subject_id: string;
  status: "pending" | "partial" | "answered" | "timed_out" | "failed";
  requested_at: string;
  partial_at: string | null;
  answered_at: string | null;
  result: Record<string, unknown>;
}
