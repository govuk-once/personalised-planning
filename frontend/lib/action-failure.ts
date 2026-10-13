import { unstable_isUnrecognizedActionError } from "next/navigation";

import { UNREACHABLE } from "@/lib/jobs";
import { pause } from "@/lib/pause";
import type { ActionResult } from "@/lib/types";

export const SITE_UPDATED = "This page has been updated. Reload the page and try again.";
const SOMETHING_WRONG = "Something went wrong. Please try again.";

export function failedCall(error: unknown): { ok: false; error: string } {
  const outdated = unstable_isUnrecognizedActionError(error);
  const message = outdated ? SITE_UPDATED : SOMETHING_WRONG;

  return {
    ok: false,
    error: message,
  };
}

const UNKNOWN_OUTCOME = new Set([UNREACHABLE, SOMETHING_WRONG]);
const ASK_AGAIN_AFTER_MS = 2_000;
const QUICK_FAILURE_MS = 10_000;

// Safe to repeat, as the backend starts a job id once. A slow failure is not asked again:
// the backend is most likely hanging and would hang again.
export async function startTwice<T>(start: () => Promise<ActionResult<T>>) {
  const startedAt = Date.now();
  const first = await start().catch(failedCall);
  const tookMs = Date.now() - startedAt;
  const quick = tookMs < QUICK_FAILURE_MS;

  if (first.ok) {
    return first;
  }

  const unknownOutcome = UNKNOWN_OUTCOME.has(first.error);

  if (!quick || !unknownOutcome) {
    return first;
  }

  await pause(ASK_AGAIN_AFTER_MS);

  return start().catch(failedCall);
}
