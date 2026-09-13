import { postJson } from "./http";

export type SampleImportResult = {
  updated_count: number;
};

export async function importSample(
  signal?: AbortSignal,
): Promise<SampleImportResult> {
  const payload = await postJson<unknown>("/api/sample/import", signal);
  if (payload !== null && typeof payload === "object") {
    const record = payload as { updated_count?: unknown };
    const count =
      typeof record.updated_count === "number" ? record.updated_count : 0;
    return { updated_count: count };
  }
  return { updated_count: 0 };
}
