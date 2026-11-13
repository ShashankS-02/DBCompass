import { apiGet } from "./client";

export type SupportStatus = "strategic" | "supported" | "sunset";
export type SpecialCase = "caching" | "vector_search" | "analytics";

export interface SupportedEngine {
  status: SupportStatus;
  label: string;
  note: string | null;
}

export interface OrgSupportConfig {
  version: number;
  last_verified: string;
  statuses: Record<SupportStatus, string>;
  engines: Record<string, SupportedEngine>;
  special_cases: Record<SpecialCase, { label: string; description: string }>;
}

export interface EngineFeature {
  feature: string;
  label: string;
  how_to_check: string;
}

export interface DiscoveryQuery {
  label: string;
  query: string;
  note: string | null;
}

export interface EngineFeatureList {
  discovery_note: string | null;
  discovery?: DiscoveryQuery[];
  features: EngineFeature[];
}

export interface EngineFeaturesConfig {
  version: number;
  last_verified: string;
  sticky_features: string[];
  engines: Record<string, EngineFeatureList>;
}

export interface IntakeConfig {
  org_support: OrgSupportConfig;
  engine_features: EngineFeaturesConfig;
  commercial_engines: string[];
}

export type ReadinessVerdict = "ready" | "needs_sme" | "needs_partner" | "unknown";

export interface Readiness {
  verdict: ReadinessVerdict;
  label: string;
  reasons: string[];
  actions: string[];
}

type TokenGetter = () => Promise<string | null>;

export function fetchIntake(getAccessToken: TokenGetter): Promise<IntakeConfig> {
  return apiGet<IntakeConfig>("/intake", getAccessToken);
}

export const READINESS_STYLES: Record<ReadinessVerdict, string> = {
  ready: "border-emerald-200 bg-emerald-50 text-emerald-900",
  needs_sme: "border-amber-200 bg-amber-50 text-amber-900",
  needs_partner: "border-rose-200 bg-rose-50 text-rose-900",
  unknown: "border-sand-200 bg-sand-50 text-slate-700",
};
