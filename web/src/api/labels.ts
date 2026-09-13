import type { ClassId, ConfirmedLabel } from "../domain/images";
import { sendDelete, sendJson } from "./http";

export async function putImageLabel(
  ref: string,
  classId: ClassId,
  signal?: AbortSignal,
): Promise<ConfirmedLabel> {
  const payload = await sendJson<unknown>(
    `/api/images/${encodeURIComponent(ref)}/label`,
    "PUT",
    { class_id: classId, source: "human" },
    signal,
  );
  if (payload !== null && typeof payload === "object") {
    const record = payload as { class_id?: unknown; source?: unknown };
    if (typeof record.class_id === "string") {
      return {
        class_id: record.class_id as ClassId,
        source:
          record.source === "model_suggested" ? "model_suggested" : "human",
      };
    }
  }
  return { class_id: classId, source: "human" };
}

export async function deleteImageLabel(
  ref: string,
  signal?: AbortSignal,
): Promise<void> {
  await sendDelete(`/api/images/${encodeURIComponent(ref)}/label`, signal);
}

export async function bulkPutLabels(
  refs: string[],
  classId: ClassId,
  signal?: AbortSignal,
): Promise<number> {
  const payload = await sendJson<unknown>(
    "/api/labels/bulk",
    "POST",
    { refs, class_id: classId },
    signal,
  );
  if (payload !== null && typeof payload === "object") {
    const record = payload as { updated_count?: unknown };
    if (typeof record.updated_count === "number") {
      return record.updated_count;
    }
  }
  return refs.length;
}
