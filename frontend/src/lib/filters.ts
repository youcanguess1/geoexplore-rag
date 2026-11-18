import type { RetrievalFilters } from "../types";

export const EMPTY_FILTERS: RetrievalFilters = {
  document_ids: [],
  data_types: [],
  document_types: [],
  languages: [],
};

function unique(values: string[], lowercase = false): string[] {
  const result: string[] = [];
  for (const value of values) {
    const cleaned = (lowercase ? value.toLowerCase() : value).trim();
    if (cleaned && !result.includes(cleaned)) result.push(cleaned);
  }
  return result;
}

export function normaliseFilters(filters: RetrievalFilters): RetrievalFilters {
  return {
    document_ids: unique(filters.document_ids),
    data_types: unique(filters.data_types) as RetrievalFilters["data_types"],
    document_types: unique(filters.document_types) as RetrievalFilters["document_types"],
    languages: unique(filters.languages, true),
  };
}

export function filtersForRequest(filters: RetrievalFilters): RetrievalFilters | undefined {
  const normalised = normaliseFilters(filters);
  return normalised.document_ids.length || normalised.data_types.length ||
    normalised.document_types.length || normalised.languages.length
    ? normalised
    : undefined;
}

export function formatFilters(filters: RetrievalFilters | null | undefined): string {
  if (!filters) return "未限制资料范围";
  const parts = [
    filters.document_ids.length ? `文档：${filters.document_ids.join("、")}` : "",
    filters.data_types.length ? `分类：${filters.data_types.join("、")}` : "",
    filters.document_types.length ? `类型：${filters.document_types.join("、")}` : "",
    filters.languages.length ? `语言：${filters.languages.join("、")}` : "",
  ].filter(Boolean);
  return parts.length ? parts.join("；") : "未限制资料范围";
}
