import type { ApiDeps, Reply } from "./api.ts";
import { errorLogFields } from "./errors.ts";
import type { GetJob } from "./events.ts";
import { BUSY, isLive } from "./jobs.ts";
import { logger } from "./log.ts";
import { publicJob } from "./views.ts";

async function findJob(event: GetJob, deps: ApiDeps): Promise<Reply> {
  const nowMs = deps.nowMs();
  const job = await deps.store.getJob(event.sessionId, event.jobId);

  if (!isLive(job, nowMs)) {
    return {
      ok: false,
      error: "not_found",
    };
  }

  const view = await publicJob(job, nowMs, deps.store);

  return {
    ok: true,
    job: view,
  };
}

export async function lookUp(event: GetJob, deps: ApiDeps): Promise<Reply> {
  try {
    return await findJob(event, deps);
  } catch (error) {
    const log = logger(deps.log, "backend-api", event.sessionId);

    log("ERROR", "Job not read", {
      job_id: event.jobId,
      ...errorLogFields(error),
    });

    return {
      ok: false,
      error: BUSY,
    };
  }
}
