import { type ActiveModel, EMPTY_STATS, type Stats } from "../domain/stats";
import { getJson } from "./http";

function asCount(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function asCountMap(value: unknown): Record<string, number> {
  if (value === null || typeof value !== "object") {
    return {};
  }
  const result: Record<string, number> = {};
  for (const [key, item] of Object.entries(value)) {
    result[key] = asCount(item);
  }
  return result;
}

function asActiveModel(value: unknown): ActiveModel | null {
  if (value === null || typeof value !== "object") {
    return null;
  }
  const record = value as {
    ref?: unknown;
    version?: unknown;
    builtin?: unknown;
  };
  if (typeof record.ref !== "string" || record.ref === "") {
    return null;
  }
  return {
    ref: record.ref,
    version: asCount(record.version),
    builtin: record.builtin === true,
  };
}

export function parseStats(payload: unknown): Stats {
  if (payload === null || typeof payload !== "object") {
    return EMPTY_STATS;
  }
  const record = payload as Record<string, unknown>;
  const activeModel = asActiveModel(record.active_model);
  const activeRef =
    typeof record.active_model_ref === "string"
      ? record.active_model_ref
      : null;
  return {
    image_count: asCount(record.image_count),
    labeled_count: asCount(record.labeled_count),
    unlabeled_count: asCount(record.unlabeled_count),
    suggestion_count: asCount(record.suggestion_count),
    per_class: asCountMap(record.per_class),
    per_split: asCountMap(record.per_split),
    active_model_ref: activeRef,
    active_model:
      activeModel ??
      (activeRef === null
        ? null
        : { ref: activeRef, version: -1, builtin: false }),
    baseline_registered: record.baseline_registered === true,
    has_active_job: record.has_active_job === true,
  };
}

export async function fetchStats(signal?: AbortSignal): Promise<Stats> {
  const payload = await getJson<unknown>("/api/stats", signal);
  return parseStats(payload);
}
