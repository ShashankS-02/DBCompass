import { apiGet, type TokenGetter } from "./client";

export interface GuideSummary {
  slug: string;
  title: string;
  summary: string;
}

export interface Guide extends GuideSummary {
  markdown: string;
}

export function fetchGuides(getAccessToken: TokenGetter): Promise<GuideSummary[]> {
  return apiGet<GuideSummary[]>("/help/guides", getAccessToken);
}

export function fetchGuide(slug: string, getAccessToken: TokenGetter): Promise<Guide> {
  return apiGet<Guide>(`/help/guides/${encodeURIComponent(slug)}`, getAccessToken);
}
