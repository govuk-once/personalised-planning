import type { Kind } from "./requests.ts";
import { failedWith, ranTooLong, waitedTooLong } from "./status-checks.ts";
import { MAX_EVENT_AGE_SECONDS, WORKER_TIMEOUT_SECONDS } from "./timing.ts";

export const TTL_SECONDS = 90 * 60;

// Past these, Lambda has dropped the event or stopped the Worker.
const GRACE_SECONDS = 30;
export const START_LIMIT_MS = (MAX_EVENT_AGE_SECONDS + GRACE_SECONDS) * 1000;
export const RUN_LIMIT_MS = (WORKER_TIMEOUT_SECONDS + GRACE_SECONDS) * 1000;

export const NEVER_STARTED = "This could not be started. Please try again.";
export const TOO_LONG = "This took too long. Please try again.";
export const SOMETHING_WRONG = "Something went wrong. Please try again.";
export const BUSY = "The planning service is busy. Please try again.";
export const TOO_LARGE_TO_SEND =
  "This conversation is too long to send. Please start again.";
export const TOO_LARGE_TO_KEEP: Record<Kind, string> = {
  chat: "The adviser's reply was too long to keep. Please try again.",
  plan: "The plan was too large to keep. Please try again.",
};

export type Status = "pending" | "running" | "done" | "failed";

export type Job = {
  session_id: string;
  job_id: string;
  kind: Kind;
  status: Status;
  created_at: number;
  run_id?: string;
  started_at?: number;
  finished_at?: number;
  expires_at: number;
  error?: string;
  result_parts?: number;
};

export type ClaimedJob = Job & {
  run_id: string;
  started_at: number;
};

export type JobStatus = {
  status: Status;
  error?: string;
};

type NewJob = {
  sessionId: string;
  jobId: string;
  kind: Kind;
  nowMs: number;
};

export function newJob({ sessionId, jobId, kind, nowMs }: NewJob): Job {
  const nowSeconds = Math.floor(nowMs / 1000);
  const expiresAt = nowSeconds + TTL_SECONDS;

  return {
    session_id: sessionId,
    job_id: jobId,
    kind,
    status: "pending",
    created_at: nowMs,
    expires_at: expiresAt,
  };
}

export function isLive(job: Job | null, nowMs: number): job is Job {
  if (job === null) {
    return false;
  }

  return job.expires_at * 1000 > nowMs;
}

export function statusOf(job: Job, nowMs: number): JobStatus {
  if (waitedTooLong(job, nowMs, START_LIMIT_MS)) {
    return failedWith(NEVER_STARTED);
  }

  if (ranTooLong(job, nowMs, RUN_LIMIT_MS)) {
    return failedWith(TOO_LONG);
  }

  if (job.status === "failed") {
    const error = job.error || SOMETHING_WRONG;

    return failedWith(error);
  }

  return { status: job.status };
}
