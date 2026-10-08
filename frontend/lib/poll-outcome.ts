import { SITE_UPDATED } from "@/lib/action-failure";
import type { ActionResult, JobState } from "@/lib/types";

export type PollSettings = {
  intervalMs: number;
  timeoutMs: number;
  missWindowMs: number;
};

type Finished<T> = {
  ok: true;
  result: T;
};

type Failure = {
  ok: false;
  error: string;
  keepJob: boolean;
};

export type Outcome<T> = Finished<T> | Failure;

function judgeMiss(error: string, missingForMs: number, settings: PollSettings): Failure | null {
  if (error === SITE_UPDATED) {
    return {
      ok: false,
      error,
      keepJob: true,
    };
  }

  if (missingForMs >= settings.missWindowMs) {
    return {
      ok: false,
      error,
      keepJob: false,
    };
  }

  return null;
}

export function judge<T>(
  reply: ActionResult<JobState<T>>,
  missingForMs: number,
  settings: PollSettings
): Outcome<T> | null {
  if (!reply.ok) {
    return judgeMiss(reply.error, missingForMs, settings);
  }

  const job = reply.data;

  if (job.status === "done") {
    return {
      ok: true,
      result: job.result,
    };
  }

  if (job.status === "failed") {
    return {
      ok: false,
      error: job.error,
      keepJob: false,
    };
  }

  return null;
}
