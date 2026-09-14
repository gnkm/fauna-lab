import {
  DEFAULT_JOB_PARAMS,
  type Job,
  type JobCreateParams,
  type JobLogEntry,
  parseJobStatus,
} from "../domain/jobs";
import { getJson, sendJson } from "./http";
import { asBoolean, asNullableString, asNumber, asString } from "./parse";

export type JobPage = {
  items: Job[];
  total: number;
};

export type JobLogPage = {
  items: JobLogEntry[];
  total: number;
};

function parseJob(payload: unknown): Job | null {
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
    status: parseJobStatus(asString(record.status)),
    current_epoch: asNumber(record.current_epoch),
    total_epochs: asNumber(record.total_epochs, 10),
    model_ref: asNullableString(record.model_ref),
    failed: asBoolean(record.failed),
  };
}

export function parseJobPage(payload: unknown): JobPage {
  if (payload === null || typeof payload !== "object") {
    return { items: [], total: 0 };
  }
  const record = payload as { items?: unknown; total?: unknown };
  const items = Array.isArray(record.items)
    ? record.items
        .map((item) => parseJob(item))
        .filter((item): item is Job => item !== null)
    : [];
  return { items, total: asNumber(record.total, items.length) };
}

function parseLog(payload: unknown): JobLogEntry | null {
  if (payload === null || typeof payload !== "object") {
    return null;
  }
  const record = payload as Record<string, unknown>;
  const epoch = asNumber(record.epoch);
  if (epoch < 1) {
    return null;
  }
  return {
    epoch,
    train_loss: asNumber(record.train_loss),
    val_loss: asNumber(record.val_loss),
    val_accuracy: asNumber(record.val_accuracy),
    duration_seconds: asNumber(record.duration_seconds),
  };
}

export function parseJobLogPage(payload: unknown): JobLogPage {
  if (payload === null || typeof payload !== "object") {
    return { items: [], total: 0 };
  }
  const record = payload as { items?: unknown; total?: unknown };
  const items = Array.isArray(record.items)
    ? record.items
        .map((item) => parseLog(item))
        .filter((item): item is JobLogEntry => item !== null)
    : [];
  return { items, total: asNumber(record.total, items.length) };
}

export async function fetchJobs(
  limit = 50,
  offset = 0,
  signal?: AbortSignal,
): Promise<JobPage> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  return parseJobPage(await getJson<unknown>(`/api/jobs?${params}`, signal));
}

export async function fetchJob(
  ref: string,
  signal?: AbortSignal,
): Promise<Job | null> {
  return parseJob(
    await getJson<unknown>(`/api/jobs/${encodeURIComponent(ref)}`, signal),
  );
}

export async function fetchJobLogs(
  ref: string,
  limit = 200,
  offset = 0,
  signal?: AbortSignal,
): Promise<JobLogPage> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  return parseJobLogPage(
    await getJson<unknown>(
      `/api/jobs/${encodeURIComponent(ref)}/logs?${params}`,
      signal,
    ),
  );
}

export async function createJob(
  params: JobCreateParams = DEFAULT_JOB_PARAMS,
  signal?: AbortSignal,
): Promise<Job> {
  const parsed = parseJob(
    await sendJson<unknown>("/api/jobs", "POST", params, signal),
  );
  if (parsed === null) {
    throw new Error("学習ジョブの応答を解釈できません。");
  }
  return parsed;
}

export async function cancelJob(
  ref: string,
  signal?: AbortSignal,
): Promise<Job> {
  const parsed = parseJob(
    await sendJson<unknown>(
      `/api/jobs/${encodeURIComponent(ref)}/cancel`,
      "POST",
      undefined,
      signal,
    ),
  );
  if (parsed === null) {
    throw new Error("中止応答を解釈できません。");
  }
  return parsed;
}
