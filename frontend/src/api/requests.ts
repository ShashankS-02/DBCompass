import { apiGet, apiGetText, apiPost, apiPut } from "./client";

type TokenGetter = () => Promise<string | null>;

export type Verdict = "not_required" | "justified" | "needs_review" | "not_justified";
export type RequestStatus = "draft" | "submitted" | "approved" | "rejected" | "sent_back";
export type RequestKind = "new_database" | "migration";

export interface ReasonSpec {
  label: string;
  weight: number;
  evidence_prompt: string | null;
}

export interface JustificationConfig {
  min_justification_chars: number;
  weak_only: string[];
  strong_reasons: string[];
  justified_points: number;
  review_points: number;
  reasons: Record<string, ReasonSpec>;
}

export interface JustificationInput {
  kind: RequestKind;
  application_name: string;
  requested_engine: string;
  assessment_id: string;
  migration_plan_id?: string | null;
  reasons: { reason_id: string; evidence?: string | null }[];
  justification_text: string;
  alternatives_considered: string;
  refactor_person_days?: [number, number] | null;
}

export interface CostedOption {
  service_id: string;
  service_name: string;
  csp: "aws" | "gcp" | "azure";
  engine: string;
  monthly_usd: number;
  licence_monthly_usd: number;
  period_cost_usd: number;
  cost_complete: boolean;
}

export interface JustificationEvaluation {
  applies: boolean;
  verdict: Verdict;
  requested_engine: string;
  reasons: { reason_id: string; label: string; status: "verified" | "evidenced" | "claimed" | "contradicted"; points: number; note: string }[];
  points: number;
  requested_option: CostedOption | null;
  alternative_option: CostedOption | null;
  months_compared: number;
  period_saving_usd: number | null;
  refactor_cost_usd: number;
  break_even_months: number | null;
  messages: string[];
  problems: string[];
}

export interface RequestEvent {
  at: string;
  actor_id: string;
  actor_name: string;
  action: string;
  note: string | null;
}

export interface DbRequest {
  id: string;
  status: RequestStatus;
  input: JustificationInput;
  evaluation: JustificationEvaluation;
  created_by: string;
  created_by_name: string;
  created_at: string;
  updated_at: string;
  events: RequestEvent[];
}

export interface DbRequestSummary {
  id: string;
  application_name: string;
  kind: RequestKind;
  requested_engine: string;
  verdict: Verdict;
  status: RequestStatus;
  created_by_name: string;
  updated_at: string;
}

export const VERDICT_STYLES: Record<Verdict, { label: string; className: string }> = {
  not_required: { label: "No justification needed", className: "bg-slate-100 text-slate-700" },
  justified: { label: "Justified", className: "bg-emerald-100 text-emerald-800" },
  needs_review: { label: "Needs architecture review", className: "bg-amber-100 text-amber-900" },
  not_justified: { label: "Not justified", className: "bg-rose-100 text-rose-800" },
};

export const STATUS_LABELS: Record<RequestStatus, string> = {
  draft: "Draft",
  submitted: "Awaiting approval",
  approved: "Approved",
  rejected: "Rejected",
  sent_back: "Sent back",
};

export const COMMERCIAL_ENGINES = ["oracle", "sql_server", "db2"];

export function fetchReasons(getAccessToken: TokenGetter): Promise<JustificationConfig> {
  return apiGet<JustificationConfig>("/justification/reasons", getAccessToken);
}

export function previewJustification(input: JustificationInput, getAccessToken: TokenGetter): Promise<JustificationEvaluation> {
  return apiPost<JustificationEvaluation>("/justification/evaluate", input, getAccessToken);
}

export function createRequest(input: JustificationInput, getAccessToken: TokenGetter): Promise<DbRequest> {
  return apiPost<DbRequest>("/requests", input, getAccessToken);
}

export function updateRequest(id: string, input: JustificationInput, getAccessToken: TokenGetter): Promise<DbRequest> {
  return apiPut<DbRequest>(`/requests/${encodeURIComponent(id)}`, input, getAccessToken);
}

export function submitRequest(id: string, getAccessToken: TokenGetter): Promise<DbRequest> {
  return apiPost<DbRequest>(`/requests/${encodeURIComponent(id)}/submit`, {}, getAccessToken);
}

export function decideRequest(id: string, decision: "approve" | "reject" | "send_back", note: string, getAccessToken: TokenGetter): Promise<DbRequest> {
  return apiPost<DbRequest>(`/requests/${encodeURIComponent(id)}/decision`, { decision, note: note || null }, getAccessToken);
}

export function fetchRequest(id: string, getAccessToken: TokenGetter): Promise<DbRequest> {
  return apiGet<DbRequest>(`/requests/${encodeURIComponent(id)}`, getAccessToken);
}

export function listRequests(scope: "mine" | "review" | "all", getAccessToken: TokenGetter): Promise<DbRequestSummary[]> {
  return apiGet<DbRequestSummary[]>(`/requests?scope=${scope}`, getAccessToken);
}

export function exportRequest(id: string, getAccessToken: TokenGetter): Promise<string> {
  return apiGetText(`/requests/${encodeURIComponent(id)}/export`, getAccessToken);
}
