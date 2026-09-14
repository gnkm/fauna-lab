import { isClassId } from "../domain/images";
import type { ClassScore, Inference } from "../domain/inferences";
import { getJson, postForm, sendJson } from "./http";
import { asBoolean, asNullableNumber, asNumber, asString } from "./parse";

export type InferencePage = {
  items: Inference[];
  total: number;
};

function parseScore(value: unknown): ClassScore | null {
  if (value === null || typeof value !== "object") {
    return null;
  }
  const record = value as { class_id?: unknown; confidence?: unknown };
  if (typeof record.class_id !== "string" || !isClassId(record.class_id)) {
    return null;
  }
  return {
    class_id: record.class_id,
    confidence: asNumber(record.confidence),
  };
}

export function parseInference(payload: unknown): Inference | null {
  if (payload === null || typeof payload !== "object") {
    return null;
  }
  const record = payload as Record<string, unknown>;
  const ref = asString(record.ref);
  const imageRef = asString(record.image_ref);
  const top = asString(record.top_class_id);
  if (ref === "" || imageRef === "" || !isClassId(top)) {
    return null;
  }
  const scores = Array.isArray(record.scores)
    ? record.scores
        .map((item) => parseScore(item))
        .filter((item): item is ClassScore => item !== null)
    : [];
  return {
    ref,
    image_ref: imageRef,
    model_ref: asString(record.model_ref),
    top_class_id: top,
    top_confidence: asNumber(record.top_confidence),
    other_mass: asNullableNumber(record.other_mass),
    low_confidence: asBoolean(record.low_confidence),
    created_at: asString(record.created_at),
    scores,
  };
}

export function parseInferencePage(payload: unknown): InferencePage {
  if (payload === null || typeof payload !== "object") {
    return { items: [], total: 0 };
  }
  const record = payload as { items?: unknown; total?: unknown };
  const items = Array.isArray(record.items)
    ? record.items
        .map((item) => parseInference(item))
        .filter((item): item is Inference => item !== null)
    : [];
  return { items, total: asNumber(record.total, items.length) };
}

export async function fetchInferences(
  limit = 50,
  offset = 0,
  signal?: AbortSignal,
): Promise<InferencePage> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  return parseInferencePage(
    await getJson<unknown>(`/api/inferences?${params}`, signal),
  );
}

export async function inferRegistered(
  refs: string[],
  signal?: AbortSignal,
): Promise<Inference[]> {
  const payload = await sendJson<unknown>(
    "/api/inferences",
    "POST",
    { refs },
    signal,
  );
  return parseInferencePage(payload).items;
}

export async function inferFiles(
  files: File[],
  signal?: AbortSignal,
): Promise<Inference[]> {
  const form = new FormData();
  for (const file of files) {
    form.append("files", file);
  }
  const payload = await postForm<unknown>("/api/inferences", form, signal);
  return parseInferencePage(payload).items;
}
