export type JobKind = "chat" | "plan";

// Inside the 150 seconds after which the backend no longer starts a job.
const START_WINDOW_MS = 120_000;

export const NOT_STARTED = "This could not be started. Please try again.";

export function newJobId(kind: JobKind): string {
  const uuid = crypto.randomUUID();
  const hex = uuid.replaceAll("-", "");

  return `${kind}-${hex}`;
}

export function freshJob(kind: JobKind) {
  const jobId = newJobId(kind);
  const startedAt = Date.now();

  return {
    jobId,
    startedAt,
    confirmed: false,
  };
}

export function stillStartable(job: { startedAt: number }, nowMs = Date.now()): boolean {
  const waitedMs = nowMs - job.startedAt;

  return waitedMs < START_WINDOW_MS;
}
