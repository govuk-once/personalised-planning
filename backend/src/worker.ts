import type { InvokeAgent } from "./agents.ts";
import type { Settings } from "./config.ts";
import { type Log, logger, type Sink } from "./log.ts";
import type { Kind } from "./requests.ts";
import { runJob } from "./run-job.ts";
import type { Store } from "./store.ts";
import { parseWorkerEvent } from "./worker-event.ts";

const NOT_CLAIMED =
  "Job not claimed: claimed already, finished, gone or too old";

export type WorkerDeps = {
  settings: Settings;
  store: Store;
  invokeAgent: InvokeAgent;
  nowMs: () => number;
  newRunId: () => string;
  log: Sink;
};

export type Run = {
  deps: WorkerDeps;
  log: Log;
  sessionId: string;
  jobId: string;
  kind: Kind;
  startedMs: number;
};

export async function handle(
  event: unknown,
  deps: WorkerDeps,
  timeoutMs: number
): Promise<void> {
  const parsed = parseWorkerEvent(event);

  if (!parsed.ok) {
    const problems = parsed.problems.join(", ");

    throw new Error(`Not a worker event: ${problems}`);
  }

  const { sessionId, jobId, kind, request } = parsed.value;
  const log = logger(deps.log, "backend-worker", sessionId);

  // A fresh run id per invocation: a duplicate delivery is a different run.
  const runId = deps.newRunId();
  const claimedMs = deps.nowMs();
  const job = await deps.store.claim(sessionId, jobId, runId, claimedMs);

  if (!job) {
    log("WARNING", NOT_CLAIMED, { job_id: jobId });

    return;
  }

  const startedMs = deps.nowMs();

  log("INFO", "Job running", {
    job_id: jobId,
    kind,
  });

  const run: Run = {
    deps,
    log,
    sessionId,
    jobId,
    kind,
    startedMs,
  };

  await runJob(run, job, request, timeoutMs);
}
