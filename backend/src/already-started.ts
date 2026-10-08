import type { ApiDeps, Reply, WorkerPayload } from "./api.ts";
import { errorLogFields } from "./errors.ts";
import { BUSY, isLive, type Job, NEVER_STARTED } from "./jobs.ts";
import type { Log } from "./log.ts";
import { refused } from "./start-replies.ts";
import { startWorker } from "./start-worker.ts";
import { statusView } from "./views.ts";

// A resend: a reload, or an SDK retry whose first reply was lost.
// A job still pending may never have reached the Worker, so start it again.
export async function alreadyStarted(
  payload: WorkerPayload,
  deps: ApiDeps,
  log: Log
): Promise<Reply> {
  const nowMs = deps.nowMs();
  let existing: Job | null;

  try {
    existing = await deps.store.getJob(payload.session_id, payload.job_id);
  } catch (error) {
    log("ERROR", "Job not read", {
      job_id: payload.job_id,
      ...errorLogFields(error),
    });

    return refused(BUSY);
  }

  if (!isLive(existing, nowMs)) {
    return refused(NEVER_STARTED);
  }

  const view = statusView(existing, nowMs);

  log("INFO", "Job already started", {
    job_id: payload.job_id,
    status: view.status,
  });

  if (view.status !== "pending") {
    return {
      ok: true,
      job: view,
    };
  }

  return startWorker(payload, deps, log);
}
