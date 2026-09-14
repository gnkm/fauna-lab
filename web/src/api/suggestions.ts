import { isClassId } from "../domain/images";
import type {
  SuggestionCreateResult,
  SuggestionItem,
  SuggestionOrder,
} from "../domain/suggestions";
import { getJson, sendJson } from "./http";
import { asNumber, asString } from "./parse";

export type SuggestionPage = {
  items: SuggestionItem[];
  total: number;
};

function parseSuggestion(payload: unknown): SuggestionItem | null {
  if (payload === null || typeof payload !== "object") {
    return null;
  }
  const record = payload as Record<string, unknown>;
  const imageRef = asString(record.image_ref);
  const classId = asString(record.class_id);
  const modelRef = asString(record.model_ref);
  if (imageRef === "" || !isClassId(classId) || modelRef === "") {
    return null;
  }
  return {
    image_ref: imageRef,
    class_id: classId,
    confidence: asNumber(record.confidence),
    model_ref: modelRef,
  };
}

export function parseSuggestionPage(payload: unknown): SuggestionPage {
  if (payload === null || typeof payload !== "object") {
    return { items: [], total: 0 };
  }
  const record = payload as { items?: unknown; total?: unknown };
  const items = Array.isArray(record.items)
    ? record.items
        .map((item) => parseSuggestion(item))
        .filter((item): item is SuggestionItem => item !== null)
    : [];
  return { items, total: asNumber(record.total, items.length) };
}

export async function fetchSuggestions(
  order: SuggestionOrder,
  limit = 200,
  offset = 0,
  signal?: AbortSignal,
): Promise<SuggestionPage> {
  const params = new URLSearchParams({
    order,
    limit: String(limit),
    offset: String(offset),
  });
  return parseSuggestionPage(
    await getJson<unknown>(`/api/suggestions?${params}`, signal),
  );
}

export async function generateSuggestions(
  refs?: string[],
  signal?: AbortSignal,
): Promise<SuggestionCreateResult> {
  const body = refs === undefined ? {} : { refs };
  const payload = await sendJson<unknown>(
    "/api/suggestions",
    "POST",
    body,
    signal,
  );
  if (payload !== null && typeof payload === "object") {
    const record = payload as {
      generated_count?: unknown;
      skipped_labeled_count?: unknown;
    };
    return {
      generated_count: asNumber(record.generated_count),
      skipped_labeled_count: asNumber(record.skipped_labeled_count),
    };
  }
  return { generated_count: 0, skipped_labeled_count: 0 };
}

async function countResult(
  path: string,
  body: unknown,
  signal?: AbortSignal,
): Promise<number> {
  const payload = await sendJson<unknown>(path, "POST", body, signal);
  if (payload !== null && typeof payload === "object") {
    const record = payload as { updated_count?: unknown };
    return asNumber(record.updated_count);
  }
  return 0;
}

export async function acceptSuggestions(
  refs: string[],
  signal?: AbortSignal,
): Promise<number> {
  return countResult("/api/suggestions/accept", { refs }, signal);
}

export async function acceptSuggestionsByThreshold(
  minConfidence: number,
  signal?: AbortSignal,
): Promise<number> {
  return countResult(
    "/api/suggestions/accept-by-threshold",
    { min_confidence: minConfidence },
    signal,
  );
}

export async function rejectSuggestions(
  refs: string[],
  signal?: AbortSignal,
): Promise<number> {
  return countResult("/api/suggestions/reject", { refs }, signal);
}
