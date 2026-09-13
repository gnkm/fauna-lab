import { sendJson } from "./http";

export type SplitRequest = {
  train_ratio: number;
  val_ratio: number;
  test_ratio: number;
  seed: number;
};

export type SplitResult = SplitRequest & {
  assigned_count: number;
  unassigned_count: number;
};

function asNumber(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

export async function createSplit(
  body: SplitRequest,
  signal?: AbortSignal,
): Promise<SplitResult> {
  const payload = await sendJson<unknown>("/api/splits", "POST", body, signal);
  if (payload !== null && typeof payload === "object") {
    const record = payload as Record<string, unknown>;
    return {
      assigned_count: asNumber(record.assigned_count, 0),
      unassigned_count: asNumber(record.unassigned_count, 0),
      seed: asNumber(record.seed, body.seed),
      train_ratio: asNumber(record.train_ratio, body.train_ratio),
      val_ratio: asNumber(record.val_ratio, body.val_ratio),
      test_ratio: asNumber(record.test_ratio, body.test_ratio),
    };
  }
  return {
    assigned_count: 0,
    unassigned_count: 0,
    ...body,
  };
}
