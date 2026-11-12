import type { AssessmentResult } from "./assessments";
import { apiPost } from "./client";
import type { RequirementsInput } from "./questions";

type TokenGetter = () => Promise<string | null>;

export interface WhatIfRequest {
  answers: Record<string, unknown>;
  priorities: Record<string, number>;
}

export interface RankMove {
  option: string;
  csp: string;
  before_rank: number | null;
  after_rank: number | null;
  before_score: number | null;
  after_score: number | null;
}

export interface WhatIfChanges {
  changed_fields: { field_id: string; label: string; before: string; after: string }[];
  top_changed: boolean;
  rank_moves: RankMove[];
  newly_filtered: { service_name: string; message: string }[];
  no_longer_filtered: string[];
  rules_added: string[];
  rules_removed: string[];
  summary: string[];
}

export interface WhatIfResult {
  base_assessment_id: string;
  input: RequirementsInput;
  outcome: Pick<AssessmentResult, "engine_version" | "recommendations" | "trace" | "pricing">;
  changes: WhatIfChanges;
}

export function runWhatIf(id: string, request: WhatIfRequest, getAccessToken: TokenGetter): Promise<WhatIfResult> {
  return apiPost<WhatIfResult>(`/assessments/${encodeURIComponent(id)}/whatif`, request, getAccessToken);
}
