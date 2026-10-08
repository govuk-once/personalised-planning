import { errorLogFields } from "./errors.ts";
import type { Run } from "./worker.ts";

// Best effort: if even this write fails, the page reports the job as taking too long.
export async function failJob(
  run: Run,
  reason: string,
  detail: Record<string, unknown> = {}
): Promise<void> {
  const { deps, log, sessionId, jobId } = run;

  log("ERROR", "Job failed", {
    job_id: jobId,
    kind: run.kind,
    reason,
    ...detail,
  });

  const nowMs = deps.nowMs();

  await deps.store.fail(sessionId, jobId, reason, nowMs).catch(error => {
    log("ERROR", "Job not marked failed", {
      job_id: jobId,
      ...errorLogFields(error),
    });
  });
}
