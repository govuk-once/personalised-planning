import type { Kind } from "./requests.ts";
import { type Job, SOMETHING_WRONG, type Status, statusOf } from "./jobs.ts";
import { joinParts } from "./results.ts";
import type { Store } from "./store.ts";

export type PublicJob = {
  job_id: string;
  kind: Kind;
  status: Status;
  result?: unknown;
  error?: string;
};

const NO_RESULT = Symbol("no result");

async function readResult(store: Store, job: Job): Promise<unknown> {
  if (!job.run_id) {
    return NO_RESULT;
  }

  const parts = await store.readResult(job.session_id, job.job_id, job.run_id);

  if (parts.length !== job.result_parts) {
    return NO_RESULT;
  }

  const text = joinParts(parts);

  try {
    return JSON.parse(text);
  } catch {
    return NO_RESULT;
  }
}

// Never includes the job's request.
export function statusView(job: Job, nowMs: number): PublicJob {
  const { status, error } = statusOf(job, nowMs);

  const view: PublicJob = {
    job_id: job.job_id,
    kind: job.kind,
    status,
  };

  if (status === "failed") {
    view.error = error;
  }

  return view;
}

export async function publicJob(
  job: Job,
  nowMs: number,
  store: Store
): Promise<PublicJob> {
  const view = statusView(job, nowMs);

  if (view.status !== "done") {
    return view;
  }

  const result = await readResult(store, job);

  if (result === NO_RESULT) {
    return {
      ...view,
      status: "failed",
      error: SOMETHING_WRONG,
    };
  }

  return {
    ...view,
    result,
  };
}
