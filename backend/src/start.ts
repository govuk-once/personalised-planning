import { alreadyStarted } from "./already-started.ts";
import type { ApiDeps, Reply } from "./api.ts";
import { errorLogFields, hasName } from "./errors.ts";
import type { StartJob } from "./events.ts";
import { NEVER_STARTED, newJob, TOO_LARGE_TO_SEND } from "./jobs.ts";
import { byteLength, MAX_WORKER_EVENT_BYTES } from "./limits.ts";
import { logger } from "./log.ts";
import { refused } from "./start-replies.ts";
import { startWorker } from "./start-worker.ts";

function jobIdFor(event: StartJob, deps: ApiDeps): string {
  if (event.jobId) {
    return event.jobId;
  }

  const id = deps.newId();

  return `${event.kind}-${id}`;
}

export async function start(event: StartJob, deps: ApiDeps): Promise<Reply> {
  const log = logger(deps.log, "backend-api", event.sessionId);
  const jobId = jobIdFor(event, deps);

  const payload = {
    session_id: event.sessionId,
    job_id: jobId,
    kind: event.kind,
    request: event.request,
  };

  const payloadBytes = byteLength(payload);

  if (payloadBytes > MAX_WORKER_EVENT_BYTES) {
    log("WARNING", "Request too large to send", {
      job_id: jobId,
      request_bytes: payloadBytes,
    });

    return refused(TOO_LARGE_TO_SEND);
  }

  const job = newJob({
    sessionId: event.sessionId,
    jobId,
    kind: event.kind,
    nowMs: deps.nowMs(),
  });

  try {
    await deps.store.putJob(job);
  } catch (error) {
    if (hasName(error, "ConditionalCheckFailedException")) {
      return alreadyStarted(payload, deps, log);
    }

    log("ERROR", "Job not stored", {
      job_id: jobId,
      ...errorLogFields(error),
    });

    return refused(NEVER_STARTED);
  }

  const reply = await startWorker(payload, deps, log);

  if (reply.ok) {
    log("INFO", "Job started", {
      job_id: jobId,
      kind: event.kind,
      request_bytes: payloadBytes,
    });
  }

  return reply;
}
