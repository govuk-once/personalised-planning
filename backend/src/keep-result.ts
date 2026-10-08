import { errorLogFields } from "./errors.ts";
import { failJob } from "./fail-job.ts";
import { type ClaimedJob, SOMETHING_WRONG } from "./jobs.ts";
import { type Shaped, summaryOf } from "./outputs.ts";
import { splitIntoParts, utf8Bytes } from "./results.ts";
import type { Run } from "./worker.ts";

export async function keepResult(
  run: Run,
  job: ClaimedJob,
  shaped: Shaped,
  text: string
): Promise<void> {
  const { deps, log } = run;
  const parts = splitIntoParts(text);
  let stored: boolean;

  try {
    const nowMs = deps.nowMs();

    stored = await deps.store.saveResult(job, parts, nowMs);
  } catch (error) {
    const detail = errorLogFields(error);

    await failJob(run, SOMETHING_WRONG, detail);
    throw error;
  }

  const elapsedMs = deps.nowMs() - run.startedMs;
  const seconds = Math.round(elapsedMs / 100) / 10;
  const resultBytes = utf8Bytes(text);
  const summary = summaryOf(run.kind, shaped);

  const fields = {
    job_id: run.jobId,
    kind: run.kind,
    seconds,
    result_bytes: resultBytes,
    result_parts: parts.length,
    ...summary,
  };

  if (stored) {
    log("INFO", "Job done", fields);

    return;
  }

  log("WARNING", "Job was no longer running", fields);
}
