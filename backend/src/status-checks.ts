import type { Job, JobStatus } from "./jobs.ts";

export function waitedTooLong(job: Job, nowMs: number, limitMs: number) {
  if (job.status !== "pending") {
    return false;
  }

  const waitedMs = nowMs - job.created_at;

  return waitedMs > limitMs;
}

export function ranTooLong(job: Job, nowMs: number, limitMs: number) {
  if (job.status !== "running") {
    return false;
  }

  const startedAt = job.started_at ?? job.created_at;
  const ranMs = nowMs - startedAt;

  return ranMs > limitMs;
}

export function failedWith(error: string): JobStatus {
  return {
    status: "failed",
    error,
  };
}
