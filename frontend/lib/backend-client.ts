export const BACKEND_URL = (process.env.BACKEND_URL ?? "http://localhost:8000").replace(/\/+$/, "");
const BACKEND_API_KEY = process.env.BACKEND_API_KEY;
const REQUEST_TIMEOUT_MS = Number(process.env.BACKEND_TIMEOUT_MS ?? 300_000);

export class BackendError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string
  ) {
    super(`Backend responded ${status}`);
    this.name = "BackendError";
  }
}

export async function callBackend<T>(path: string, sessionId: string, body?: unknown): Promise<T> {
  const response = await fetch(`${BACKEND_URL}${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Session-Id": sessionId,
      ...(BACKEND_API_KEY ? { "X-Api-Key": BACKEND_API_KEY } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    cache: "no-store",
  });

  if (!response.ok) {
    throw new BackendError(response.status, await response.text());
  }

  return (await response.json()) as T;
}

function detailFrom(body: string): string | null {
  try {
    return (JSON.parse(body) as { detail?: string }).detail ?? null;
  } catch {
    return null;
  }
}

export function describeFailure(error: unknown): string {
  if (error instanceof BackendError) {
    return detailFrom(error.detail) ?? `The service responded with an error (${error.status}).`;
  }

  if (error instanceof Error && error.name === "TimeoutError") {
    return "The request took too long and was cancelled. Please try again.";
  }

  if (error instanceof Error && error.message.includes("fetch failed")) {
    return "Could not reach the planning service. Is the backend running?";
  }

  return "Something went wrong. Please try again.";
}
