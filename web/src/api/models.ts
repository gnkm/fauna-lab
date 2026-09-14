import { isClassId } from "../domain/images";
import type { ClassMetric, ModelMetrics, ModelVersion } from "../domain/models";
import { CLASS_IDS } from "../domain/models";
import { getJson, sendDelete, sendJson } from "./http";
import { asBoolean, asNumber, asString } from "./parse";

export type ModelPage = {
  items: ModelVersion[];
  total: number;
};

function parseClassMetric(value: unknown): ClassMetric | null {
  if (value === null || typeof value !== "object") {
    return null;
  }
  const record = value as Record<string, unknown>;
  return {
    precision: asNumber(record.precision),
    recall: asNumber(record.recall),
    f1: asNumber(record.f1),
    support: asNumber(record.support),
  };
}

function parseMetrics(value: unknown): ModelMetrics | null {
  if (value === null || typeof value !== "object") {
    return null;
  }
  const record = value as Record<string, unknown>;
  const perClassRaw =
    record.per_class !== null && typeof record.per_class === "object"
      ? (record.per_class as Record<string, unknown>)
      : {};
  const per_class = {} as ModelMetrics["per_class"];
  for (const classId of CLASS_IDS) {
    const metric = parseClassMetric(perClassRaw[classId]);
    if (metric === null) {
      return null;
    }
    per_class[classId] = metric;
  }
  const matrixRaw =
    record.confusion_matrix !== null &&
    typeof record.confusion_matrix === "object"
      ? (record.confusion_matrix as {
          labels?: unknown;
          matrix?: unknown;
        })
      : null;
  const labels = Array.isArray(matrixRaw?.labels)
    ? matrixRaw.labels.filter(
        (item): item is ModelMetrics["confusion_matrix"]["labels"][number] =>
          typeof item === "string" && isClassId(item),
      )
    : [...CLASS_IDS];
  const matrix = Array.isArray(matrixRaw?.matrix)
    ? matrixRaw.matrix.map((row) =>
        Array.isArray(row)
          ? row.map((cell) => asNumber(cell))
          : CLASS_IDS.map(() => 0),
      )
    : CLASS_IDS.map(() => CLASS_IDS.map(() => 0));
  return {
    accuracy: asNumber(record.accuracy),
    per_class,
    confusion_matrix: { labels, matrix },
  };
}

export function parseModel(payload: unknown): ModelVersion | null {
  if (payload === null || typeof payload !== "object") {
    return null;
  }
  const record = payload as Record<string, unknown>;
  const ref = asString(record.ref);
  if (ref === "") {
    return null;
  }
  return {
    ref,
    version: asNumber(record.version),
    builtin: asBoolean(record.builtin),
    active: asBoolean(record.active),
    created_at: asString(record.created_at),
    metrics: parseMetrics(record.metrics),
  };
}

export function parseModelPage(payload: unknown): ModelPage {
  if (payload === null || typeof payload !== "object") {
    return { items: [], total: 0 };
  }
  const record = payload as { items?: unknown; total?: unknown };
  const items = Array.isArray(record.items)
    ? record.items
        .map((item) => parseModel(item))
        .filter((item): item is ModelVersion => item !== null)
    : [];
  return { items, total: asNumber(record.total, items.length) };
}

export async function fetchModels(
  limit = 50,
  offset = 0,
  signal?: AbortSignal,
): Promise<ModelPage> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  return parseModelPage(
    await getJson<unknown>(`/api/models?${params}`, signal),
  );
}

export async function fetchModel(
  ref: string,
  signal?: AbortSignal,
): Promise<ModelVersion | null> {
  return parseModel(
    await getJson<unknown>(`/api/models/${encodeURIComponent(ref)}`, signal),
  );
}

export async function activateModel(
  ref: string,
  signal?: AbortSignal,
): Promise<ModelVersion> {
  const parsed = parseModel(
    await sendJson<unknown>(
      `/api/models/${encodeURIComponent(ref)}/activate`,
      "POST",
      undefined,
      signal,
    ),
  );
  if (parsed === null) {
    throw new Error("有効化の応答を解釈できません。");
  }
  return parsed;
}

export async function evaluateModel(
  ref: string,
  signal?: AbortSignal,
): Promise<ModelVersion> {
  const parsed = parseModel(
    await sendJson<unknown>(
      `/api/models/${encodeURIComponent(ref)}/evaluate`,
      "POST",
      undefined,
      signal,
    ),
  );
  if (parsed === null) {
    throw new Error("再評価の応答を解釈できません。");
  }
  return parsed;
}

export async function deleteModel(
  ref: string,
  signal?: AbortSignal,
): Promise<void> {
  await sendDelete(`/api/models/${encodeURIComponent(ref)}`, signal);
}
