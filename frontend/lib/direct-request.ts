import type { ActionResult, BackendRequest } from "@/lib/types";

// Bypass amplify compute limits

class BackendRefused extends Error {}
class TimedOut extends Error {}

function detailFrom(body: string): string | null {
  try {
    const { detail } = JSON.parse(body) as { detail?: unknown };
    return typeof detail === "string" ? detail : null;
  } catch {
    return null;
  }
}

export async function callDirect<T>(
  target: BackendRequest,
  sessionId: string,
  timeoutMs: number
): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(target.url, {
      method: target.body ? "POST" : "GET",
      headers: {
        "Content-Type": "application/json",
        "X-Session-Id": sessionId,
        ...(target.ticket ? { "X-Plan-Ticket": target.ticket } : {}),
      },
      body: target.body ? JSON.stringify(target.body) : undefined,
      signal: controller.signal,
    });

    if (!response.ok) {
      const detail = detailFrom(await response.text());
      throw new BackendRefused(
        detail ?? `The planning service responded with an error (${response.status}).`
      );
    }

    return (await response.json()) as T;
  } catch (error) {
    throw controller.signal.aborted ? new TimedOut() : error;
  } finally {
    clearTimeout(timer);
  }
}

export function describeDirectFailure(error: unknown, tooLong: string): string {
  if (error instanceof TimedOut) return tooLong;
  if (error instanceof BackendRefused) return error.message;
  if (error instanceof TypeError) return "Could not reach the planning service. Please try again.";
  return "Something went wrong. Please try again.";
}

export async function attemptDirect<T>(
  target: BackendRequest,
  sessionId: string,
  { timeoutMs, tooLong }: { timeoutMs: number; tooLong: string }
): Promise<ActionResult<T>> {
  try {
    return { ok: true, data: await callDirect<T>(target, sessionId, timeoutMs) };
  } catch (error) {
    return { ok: false, error: describeDirectFailure(error, tooLong) };
  }
}
