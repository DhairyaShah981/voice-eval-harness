// Mirror of voice_eval_harness/core/models.py — field-for-field so report.json
// payloads round-trip without transformation.

export type Role = "user" | "agent" | "tool" | "system";

export interface TranscriptEvent {
  ts_ms: number;
  role: Role;
  text: string | null;
  tool_name: string | null;
  tool_args: Record<string, unknown> | null;
  audio_uri?: string | null;
  extra?: Record<string, unknown>;
}

export interface AssertionResult {
  kind: string;
  passed: boolean;
  detail: string;
}

export interface RunResult {
  case_id: string;
  passed: boolean;
  duration_ms: number;
  transcript: TranscriptEvent[];
  assertion_results: AssertionResult[];
  cost_usd: number;
  error: string | null;
}

export interface SuiteResult {
  cases: RunResult[];
  total_cost_usd: number;
}

// Dashboard-level row shape (joined view from `runs` table).
export interface RunRow {
  id: string;
  suite_hash: string;
  started_at: string;
  total_cost_usd: number;
  pass_count: number;
  fail_count: number;
  raw_report?: SuiteResult;
}
