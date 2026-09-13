import {
  type ConfirmedLabel,
  type ImageFilters,
  type ImageItem,
  isClassId,
  isSplitId,
  type Suggestion,
  type UploadItem,
} from "../domain/images";
import { ApiError, getJson, readProblem, sendDelete } from "./http";

export type ImagePage = {
  items: ImageItem[];
  total: number;
};

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function asNumber(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function asLabel(value: unknown): ConfirmedLabel | null {
  if (value === null || typeof value !== "object") {
    return null;
  }
  const record = value as { class_id?: unknown; source?: unknown };
  if (typeof record.class_id !== "string" || !isClassId(record.class_id)) {
    return null;
  }
  const source =
    record.source === "model_suggested" ? "model_suggested" : "human";
  return { class_id: record.class_id, source };
}

function asSuggestion(value: unknown): Suggestion | null {
  if (value === null || typeof value !== "object") {
    return null;
  }
  const record = value as {
    class_id?: unknown;
    confidence?: unknown;
    model_ref?: unknown;
  };
  if (typeof record.class_id !== "string" || !isClassId(record.class_id)) {
    return null;
  }
  if (typeof record.model_ref !== "string" || record.model_ref === "") {
    return null;
  }
  return {
    class_id: record.class_id,
    confidence: asNumber(record.confidence),
    model_ref: record.model_ref,
  };
}

export function parseImage(payload: unknown): ImageItem | null {
  if (payload === null || typeof payload !== "object") {
    return null;
  }
  const record = payload as Record<string, unknown>;
  const ref = asString(record.ref);
  const split = asString(record.split);
  if (ref === "" || !isSplitId(split)) {
    return null;
  }
  return {
    ref,
    sha256: asString(record.sha256),
    split,
    label: asLabel(record.label),
    suggestion: asSuggestion(record.suggestion),
    original_name: asString(record.original_name),
    size_bytes: asNumber(record.size_bytes),
    width: asNumber(record.width),
    height: asNumber(record.height),
    created_at: asString(record.created_at),
    media_type: asString(record.media_type),
  };
}

export function parseImagePage(payload: unknown): ImagePage {
  if (payload === null || typeof payload !== "object") {
    return { items: [], total: 0 };
  }
  const record = payload as { items?: unknown; total?: unknown };
  const items = Array.isArray(record.items)
    ? record.items
        .map((item) => parseImage(item))
        .filter((item): item is ImageItem => item !== null)
    : [];
  return { items, total: asNumber(record.total, items.length) };
}

export function buildImageQuery(
  filters: ImageFilters,
  limit: number,
  offset: number,
): string {
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  if (filters.labeled === "yes") {
    params.set("labeled", "true");
  } else if (filters.labeled === "no") {
    params.set("labeled", "false");
  }
  if (filters.classId !== "") {
    params.set("class_id", filters.classId);
  }
  if (filters.split !== "") {
    params.set("split", filters.split);
  }
  return params.toString();
}

export async function fetchImages(
  filters: ImageFilters,
  limit = 200,
  offset = 0,
  signal?: AbortSignal,
): Promise<ImagePage> {
  const query = buildImageQuery(filters, limit, offset);
  const payload = await getJson<unknown>(`/api/images?${query}`, signal);
  return parseImagePage(payload);
}

export async function fetchImage(
  ref: string,
  signal?: AbortSignal,
): Promise<ImageItem> {
  const payload = await getJson<unknown>(
    `/api/images/${encodeURIComponent(ref)}`,
    signal,
  );
  const image = parseImage(payload);
  if (image === null) {
    throw new ApiError(500, "internal_error", "画像の応答を解釈できません。");
  }
  return image;
}

export async function deleteImage(
  ref: string,
  signal?: AbortSignal,
): Promise<void> {
  await sendDelete(`/api/images/${encodeURIComponent(ref)}`, signal);
}

function parseUploadItem(value: unknown): UploadItem | null {
  if (value === null || typeof value !== "object") {
    return null;
  }
  const record = value as {
    filename?: unknown;
    ok?: unknown;
    ref?: unknown;
    code?: unknown;
    detail?: unknown;
  };
  const filename = asString(record.filename);
  if (filename === "") {
    return null;
  }
  const ok = record.ok === true;
  return {
    filename,
    ok,
    ref: typeof record.ref === "string" ? record.ref : undefined,
    code: typeof record.code === "string" ? record.code : undefined,
    detail: typeof record.detail === "string" ? record.detail : undefined,
  };
}

export async function uploadImages(
  files: File[],
  signal?: AbortSignal,
): Promise<UploadItem[]> {
  const form = new FormData();
  for (const file of files) {
    form.append("files", file);
  }
  const response = await fetch("/api/images", {
    method: "POST",
    headers: { Accept: "application/json" },
    body: form,
    signal,
  });
  if (!response.ok) {
    const error = await readProblem(response);
    const names = files.map((file) => file.name);
    if (names.length === 1) {
      return [
        {
          filename: names[0] ?? "file",
          ok: false,
          code: error.code,
          detail: error.message,
        },
      ];
    }
    throw error;
  }
  const payload: unknown = await response.json();
  if (payload !== null && typeof payload === "object") {
    const record = payload as { items?: unknown };
    if (Array.isArray(record.items)) {
      return record.items
        .map((item) => parseUploadItem(item))
        .filter((item): item is UploadItem => item !== null);
    }
  }
  return [];
}
