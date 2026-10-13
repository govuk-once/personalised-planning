import { failedCall } from "@/lib/action-failure";
import { pause } from "@/lib/pause";
import { judge, type Outcome, type PollSettings } from "@/lib/poll-outcome";
import type { ActionResult, JobState } from "@/lib/types";

export { judge, type Outcome, type PollSettings };

const TOO_LONG = "This took too long. Please try again.";
const MAX_BACKOFF_MS = 10_000;

type Misses = {
  count: number;
  since: number | null;
};

const NO_MISSES: Misses = {
  count: 0,
  since: null,
};

function afterReply(misses: Misses, ok: boolean, now: number): Misses {
  if (ok) {
    return NO_MISSES;
  }

  const since = misses.since ?? now;

  return {
    count: misses.count + 1,
    since,
  };
}

function missingFor(misses: Misses, now: number): number {
  if (misses.since === null) {
    return 0;
  }

  return now - misses.since;
}

function backoff(intervalMs: number, misses: number): number {
  const growing = intervalMs * 2 ** misses;

  return Math.min(growing, MAX_BACKOFF_MS);
}

export async function pollJob<T>(
  check: () => Promise<ActionResult<JobState<T>>>,
  startedAt: number,
  settings: PollSettings,
  cancelled: () => boolean
): Promise<Outcome<T> | null> {
  let misses = NO_MISSES;

  while (!cancelled()) {
    const reply = await check().catch(failedCall);

    if (cancelled()) {
      return null;
    }

    const now = Date.now();
    misses = afterReply(misses, reply.ok, now);

    const missingForMs = missingFor(misses, now);
    const outcome = judge(reply, missingForMs, settings);

    if (outcome) {
      return outcome;
    }

    const elapsedMs = now - startedAt;

    if (elapsedMs > settings.timeoutMs) {
      return {
        ok: false,
        error: TOO_LONG,
        keepJob: false,
      };
    }

    const delayMs = backoff(settings.intervalMs, misses.count);
    await pause(delayMs);
  }

  return null;
}
