import { apiGet, apiPost } from "./client";
import type { Readiness } from "./intake";
import type { AssumedField, RequirementsInput } from "./questions";

export interface SizingResult {
  vcpu: number;
  memory_gb: number;
  iops: number;
  instance_class: string;
  storage_tier: string;
  topology: "single_az" | "multi_az" | "multi_region";
  ha_topology: string;
  replicas: number;
  node_count: number;
  engine: string;
  relative_cost_units: number;
  notes: string[];
}

export interface ServiceChoice {
  service_id: string;
  service_name: string;
  role: string;
  engine: string;
  engine_version: string | null;
  instance_class: string;
  storage_tier: string;
  replicas: number;
  sizing: SizingResult;
  reason: string;
}

export interface CostLine {
  component: string;
  description: string;
  quantity: number;
  unit: string;
  unit_usd: number;
  monthly_usd: number;
  sku: string;
  region: string;
  term: string;
}

export type ComponentStatus = "priced" | "included" | "estimated" | "not_priced" | "not_applicable";

export interface CostComponent {
  id: string;
  label: string;
  status: ComponentStatus;
  monthly_usd: number | null;
  note: string;
  service: string | null;
}

export interface CostEstimate {
  tier: string;
  label: string;
  monthly_usd: number;
  lines: CostLine[];
  environment_multiplier: number;
  complete: boolean;
  missing: string[];
  notes: string[];
  components: CostComponent[];
}

export interface Baseline {
  csp: "aws" | "gcp" | "azure";
  service_id: string;
  service_name: string;
  engine: string;
  engine_label: string;
  core_monthly_usd: number | null;
  total_monthly_usd: number | null;
  priced: boolean;
  note: string;
}

export interface BaselineDelta {
  baseline_service_id: string;
  baseline_service_name: string;
  engine_label: string;
  baseline_core_usd: number | null;
  recommendation_core_usd: number | null;
  delta_usd: number | null;
  same_service: boolean;
  message: string;
}

export interface PricingSummary {
  prices_as_of: Record<string, string>;
  inr_per_usd: number | null;
  inr_rate_date: string;
  notes: string[];
}

export interface Recommendation {
  rank: number;
  components: ServiceChoice[];
  csp: "aws" | "gcp" | "azure";
  total_score: number;
  dimension_scores: Record<string, number>;
  relative_cost_units: number;
  cost_tiers: Record<string, CostEstimate>;
  ha_topology: string;
  design_guidance: string[];
  why: string[];
  explanation: string;
  versus_baseline: BaselineDelta | null;
}

export interface FilterReason {
  service_id: string;
  rule_id: string;
  message: string;
}

export interface ServiceScore {
  service_id: string;
  dimension_scores: Record<string, number>;
  weighted_score: number;
  adjustments: { rule_id: string; points: number; message: string }[];
  total_score: number;
}

export interface Trace {
  rules_fired: string[];
  filtered_out: FilterReason[];
  assumed_fields: AssumedField[];
  dimension_weights: Record<string, number>;
  scores: ServiceScore[];
  combination_notes: string[];
}

export interface AssessmentResult {
  id: string;
  created_at: string;
  created_by: string;
  input: RequirementsInput;
  engine_version: string;
  recommendations: Recommendation[];
  trace: Trace;
  pricing: PricingSummary | null;
  readiness: Readiness | null;
  baselines: Record<string, Baseline>;
}

export interface AssessmentSummary {
  id: string;
  created_at: string;
  app_name: string | null;
  app_type: string | null;
  top_recommendation: string | null;
  top_csp: "aws" | "gcp" | "azure" | null;
}

type TokenGetter = () => Promise<string | null>;

export function createAssessment(input: RequirementsInput, getAccessToken: TokenGetter): Promise<AssessmentResult> {
  return apiPost<AssessmentResult>("/assessments", input, getAccessToken);
}

export function fetchAssessment(id: string, getAccessToken: TokenGetter): Promise<AssessmentResult> {
  return apiGet<AssessmentResult>(`/assessments/${encodeURIComponent(id)}`, getAccessToken);
}

export function fetchHistory(getAccessToken: TokenGetter): Promise<AssessmentSummary[]> {
  return apiGet<AssessmentSummary[]>("/assessments", getAccessToken);
}

export const CSP_LABELS: Record<string, string> = { aws: "AWS", gcp: "Google Cloud", azure: "Azure" };

export const ROLE_LABELS: Record<string, string> = {
  primary_oltp: "Primary",
  cache: "Cache",
  search: "Search",
  analytics: "Analytics",
  vector: "Vector",
  time_series: "Time series",
};
