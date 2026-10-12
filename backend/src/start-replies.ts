import type { Reply, WorkerPayload } from "./api.ts";

export function refused(error: string): Reply {
  return {
    ok: false,
    error,
  };
}

export function started(payload: WorkerPayload): Reply {
  return {
    ok: true,
    job: {
      job_id: payload.job_id,
      kind: payload.kind,
      status: "pending",
    },
  };
}
