import { apiGet, apiPost } from "./client";
import type { Answers } from "./questions";

export interface InferredField {
  value: unknown;
  confidence: number;
  evidence: string[];
  source: "static" | "readme" | "llm" | null;
  hint: string | null;
}

export interface OracleFeatureCount {
  feature: string;
  label: string;
  count: number;
  effort: string;
  person_days_low: number;
  person_days_high: number;
  evidence: string[];
}

export interface OracleCompatibilityReport {
  plsql_lines: number;
  features: OracleFeatureCount[];
  estimated_refactor_person_days_low: number;
  estimated_refactor_person_days_high: number;
  summary: string;
}

export interface InferredRequirements {
  repo_url: string;
  ref: string | null;
  commit_sha: string | null;
  analyzer_version: string;
  fields: Record<string, InferredField>;
  prefill: Answers;
  oracle_report: OracleCompatibilityReport | null;
  summary: { files_scanned: number; files_skipped: number; bytes_scanned: number; detected: string[] };
  llm_used: boolean;
  warnings: string[];
}

export interface RepoPrefill {
  answers: Answers;
  evidence: Record<string, { confidence: number; evidence: string[] }>;
  repoUrl: string;
}

type TokenGetter = () => Promise<string | null>;

export function analyzeRepo(
  body: { repo_url: string; branch?: string; token?: string },
  getAccessToken: TokenGetter,
): Promise<InferredRequirements> {
  return apiPost<InferredRequirements>("/repo/analyze", body, getAccessToken);
}

export function listSamples(getAccessToken: TokenGetter): Promise<string[]> {
  return apiGet<string[]>("/repo/samples", getAccessToken);
}
