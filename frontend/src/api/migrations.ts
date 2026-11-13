import { apiGet, apiPost } from "./client";
import type { Answers } from "./questions";

type TokenGetter = () => Promise<string | null>;
type Csp = "aws" | "gcp" | "azure";
type Severity = "low" | "medium" | "high";

export interface MigrationPlanRequest {
  assessment_id?: string | null;
  answers?: Answers;
  target_service_id?: string | null;
  refactor_person_days?: [number, number] | null;
  team_size?: number | null;
  start_date?: string | null;
}

export interface StrategyOption {
  strategy: string;
  label: string;
  target_service_id: string;
  target_name: string;
  csp: Csp;
  engine: string;
  monthly_usd: number;
  licence_monthly_usd: number;
  cost_complete: boolean;
  effort_person_days: [number, number];
  total_cost_usd: number;
  duration_weeks: number;
  finish_date: string;
  fits_deadline: boolean;
  risk_level: Severity;
  notes: string[];
  recommended: boolean;
}

export interface ToolRef {
  id: string;
  name: string;
  url: string;
  review: string | null;
}

export interface MigrationPlan {
  id: string;
  created_at: string;
  request: MigrationPlanRequest;
  source: { platform: string | null; engine: string | null; version: string | null; size_gb: number | null };
  target_service_id: string;
  target_name: string;
  strategy: string;
  strategies: StrategyOption[];
  considered: { strategy: string; label: string; applies: boolean; reason: string }[];
  two_step: string | null;
  method: {
    method: string;
    label: string;
    reason: string;
    homogeneous: boolean;
    transfer_hours: number | null;
    daily_capacity_gb: number | null;
    cdc_feasible: boolean | null;
    needs_offline_device: boolean;
  };
  tools: { assessment: ToolRef[]; schema_conversion: ToolRef[]; data_movement: ToolRef[]; validation: ToolRef[]; supporting: ToolRef[] };
  phases: { order: number; id: string; name: string; owner_role: string; duration_days: number; tasks: string[]; go_no_go: string[] }[];
  total_duration_weeks: number;
  start_date: string;
  deadline: string;
  fits_deadline: boolean;
  risks: { id: string; severity: Severity; title: string; impact: string; mitigation: string }[];
  rollback: { approach: string; triggers: string[] };
  validation: string[];
  assumptions: string[];
}

export function createPlan(request: MigrationPlanRequest, getAccessToken: TokenGetter): Promise<MigrationPlan> {
  return apiPost<MigrationPlan>("/migrations/plan", request, getAccessToken);
}

export function fetchPlan(id: string, getAccessToken: TokenGetter): Promise<MigrationPlan> {
  return apiGet<MigrationPlan>(`/migrations/${encodeURIComponent(id)}`, getAccessToken);
}
