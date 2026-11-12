import { apiGet, apiGetFile, apiPost } from "./client";

type TokenGetter = () => Promise<string | null>;

export interface Explanation {
  assessment_id: string;
  paragraphs: string[];
  source: "llm" | "rules";
  model: string | null;
  prompt_version: string;
  generated_at: string;
  notes: string[];
}

export interface AnswerOut {
  question: string;
  answer: string;
  answerable: boolean;
  source: "llm" | "unavailable";
  notes: string[];
}

export function fetchExplanation(id: string, getAccessToken: TokenGetter): Promise<Explanation | null> {
  return apiGet<Explanation | null>(`/assessments/${encodeURIComponent(id)}/explanation`, getAccessToken);
}

export function createExplanation(id: string, refresh: boolean, getAccessToken: TokenGetter): Promise<Explanation> {
  return apiPost<Explanation>(`/assessments/${encodeURIComponent(id)}/explanation${refresh ? "?refresh=true" : ""}`, {}, getAccessToken);
}

export function askQuestion(id: string, question: string, getAccessToken: TokenGetter): Promise<AnswerOut> {
  return apiPost<AnswerOut>(`/assessments/${encodeURIComponent(id)}/ask`, { question }, getAccessToken);
}

export type ExportFormat = "md" | "pdf";

/** Fetches the design document with the auth header and hands it to the browser as a download. */
export async function downloadDesignDocument(id: string, format: ExportFormat, getAccessToken: TokenGetter): Promise<void> {
  const { blob, filename } = await apiGetFile(`/assessments/${encodeURIComponent(id)}/export?format=${format}`, getAccessToken);
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename ?? `dbcompass-design.${format}`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
