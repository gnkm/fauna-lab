export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export async function readProblem(response: Response): Promise<ApiError> {
  try {
    const body: unknown = await response.json();
    if (body !== null && typeof body === "object") {
      const record = body as {
        detail?: unknown;
        code?: unknown;
        title?: unknown;
      };
      const detail =
        typeof record.detail === "string" && record.detail.trim() !== ""
          ? record.detail
          : typeof record.title === "string"
            ? record.title
            : response.statusText;
      const code =
        typeof record.code === "string" && record.code !== ""
          ? record.code
          : "unknown";
      return new ApiError(response.status, code, detail);
    }
  } catch {
    // 本文が JSON でない場合はステータスだけで示す。
  }
  return new ApiError(
    response.status,
    "unknown",
    response.statusText || `HTTP ${String(response.status)}`,
  );
}

export async function getJson<T>(
  path: string,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(path, {
    method: "GET",
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) {
    throw await readProblem(response);
  }
  return (await response.json()) as T;
}

export async function postJson<T>(
  path: string,
  signal?: AbortSignal,
): Promise<T> {
  return sendJson<T>(path, "POST", undefined, signal);
}

export async function sendJson<T>(
  path: string,
  method: "POST" | "PUT",
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  const init: RequestInit = { method, headers, signal };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  const response = await fetch(path, init);
  if (!response.ok) {
    throw await readProblem(response);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  const text = await response.text();
  if (text.trim() === "") {
    return undefined as T;
  }
  return JSON.parse(text) as T;
}

export async function sendDelete(
  path: string,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(path, {
    method: "DELETE",
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) {
    throw await readProblem(response);
  }
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  if (error instanceof Error && error.name === "AbortError") {
    return "要求が中断されました。";
  }
  if (error instanceof Error && error.message !== "") {
    return error.message;
  }
  return "処理に失敗しました。";
}
