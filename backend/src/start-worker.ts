import type { ApiDeps, Reply, WorkerPayload } from "./api.ts";
import { errorLogFields } from "./errors.ts";
import { NEVER_STARTED } from "./jobs.ts";
import type { Log } from "./log.ts";
import { refused, started } from "./start-replies.ts";

// Lambda may have taken the event even though the call to it failed.
async function workerNotStarted(
  payload: WorkerPayload,
  deps: ApiDeps,
  log: Log
): Promise<Reply> {
  const sessionId = payload.session_id;
  const jobId = payload.job_id;
  const nowMs = deps.nowMs();

  const stopped = await deps.store
    .markNeverStarted(sessionId, jobId, NEVER_STARTED, nowMs)
    .catch(() => true);

  if (stopped) {
    return refused(NEVER_STARTED);
  }

  const job = await deps.store.getJob(sessionId, jobId).catch(() => null);

  const status = job?.status;
  const claimed = status === "running" || status === "done";

  if (!claimed) {
    return refused(NEVER_STARTED);
  }

  log("INFO", "Job started after all", { job_id: jobId });

  return started(payload);
}

export async function startWorker(
  payload: WorkerPayload,
  deps: ApiDeps,
  log: Log
): Promise<Reply> {
  try {
    await deps.startWorker(payload);

    return started(payload);
  } catch (error) {
    log("ERROR", "Worker not started", {
      job_id: payload.job_id,
      ...errorLogFields(error),
    });

    return workerNotStarted(payload, deps, log);
  }
}
