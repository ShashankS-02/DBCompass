import { apiGet, apiPost } from "./client";

export type FieldType =
  | "single_select"
  | "multi_select"
  | "number"
  | "boolean"
  | "text"
  | "list"
  | "money"
  | "engine_version";

export type FormMode = "quick" | "expert";

export interface QuestionOption {
  value: string;
  label: string;
  exclusive: boolean;
}

export interface Question {
  id: string;
  label: string;
  type: FieldType;
  why: string;
  quick: boolean;
  options: QuestionOption[];
  unit: string | null;
  min: number | null;
  max: number | null;
  integer: boolean;
  placeholder: string | null;
  tier_defaults: Record<string, unknown> | null;
}

export interface Section {
  id: string;
  title: string;
  description: string | null;
  migration_only: boolean;
  questions: Question[];
}

export interface PrioritySlider {
  id: string;
  label: string;
  dimension: string;
  default: number;
  description: string;
}

export interface QuestionSchema {
  mode: FormMode;
  sections: Section[];
  priority_sliders: PrioritySlider[];
  fixed_dimension_weights: Record<string, number>;
  default_tier: string;
}

export type Answers = Record<string, unknown>;

export interface RequirementsInput {
  mode: FormMode;
  migrating: boolean;
  answers: Answers;
  priorities: Record<string, number>;
}

export interface FieldError {
  field_id: string;
  message: string;
}

export interface AssumedField {
  field_id: string;
  value: unknown;
  reason: string;
}

export interface ValidationReport {
  valid: boolean;
  errors: FieldError[];
  normalised: RequirementsInput;
  unanswered_quick_fields: string[];
  assumed_fields: AssumedField[];
  ignored_fields: string[];
  dimension_weights: Record<string, number>;
}

type TokenGetter = () => Promise<string | null>;

export function fetchQuestions(mode: FormMode, getAccessToken: TokenGetter): Promise<QuestionSchema> {
  return apiGet<QuestionSchema>(`/questions?mode=${mode}`, getAccessToken);
}

export function validateRequirements(
  requirements: RequirementsInput,
  getAccessToken: TokenGetter,
): Promise<ValidationReport> {
  return apiPost<ValidationReport>("/requirements/validate", requirements, getAccessToken);
}

/** Human-readable form of an answer or default value, using option labels where possible. */
export function describeValue(question: Question | undefined, value: unknown): string {
  if (value === null || value === undefined) {
    return "—";
  }
  const labelFor = (optionValue: unknown) =>
    question?.options.find((option) => option.value === optionValue)?.label ?? String(optionValue);

  if (Array.isArray(value)) {
    return value.map(labelFor).join(", ");
  }
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    if ("amount" in record) {
      return `${record.amount} ${String(record.currency ?? "usd").toUpperCase()}`;
    }
    if ("engine" in record) {
      return [labelFor(record.engine), record.version].filter(Boolean).join(" ");
    }
  }
  const text = labelFor(value);
  return question?.unit ? `${text} ${question.unit}` : text;
}

/** Mirror of backend app/engine/weights.py, for live display while dragging sliders. */
export function computeDimensionWeights(
  priorities: Record<string, number>,
  sliders: PrioritySlider[],
  fixedWeights: Record<string, number>,
): Record<string, number> {
  const fixedTotal = Object.values(fixedWeights).reduce((sum, weight) => sum + weight, 0);
  const sliderShare = 1 - fixedTotal;
  const sliderTotal = sliders.reduce((sum, slider) => sum + (priorities[slider.id] ?? slider.default), 0);

  const weights: Record<string, number> = {};
  for (const slider of sliders) {
    const fraction =
      sliderTotal === 0 ? 1 / sliders.length : (priorities[slider.id] ?? slider.default) / sliderTotal;
    weights[slider.dimension] = (weights[slider.dimension] ?? 0) + sliderShare * fraction;
  }
  for (const [dimension, weight] of Object.entries(fixedWeights)) {
    weights[dimension] = (weights[dimension] ?? 0) + weight;
  }
  return weights;
}
