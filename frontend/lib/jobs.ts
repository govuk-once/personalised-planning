import type { ActionResult, JobRef, JobState } from "@/lib/types";

export type BackendJob = {
  job_id: string;
  kind: "chat" | "plan";
  status: "pending" | "running" | "done" | "failed";
  result?: unknown;
  error?: string;
};

type BackendSuccess = {
  ok: true;
  job: BackendJob;
};

type BackendRefusal = {
  ok: false;
  error: string;
};

export type BackendReply = BackendSuccess | BackendRefusal;

export const UNREACHABLE = "Could not reach the planning service. Please try again.";
const LOST = "We lost track of that request. Please try again.";

const REFUSALS: Record<string, string> = {
  invalid_request: "That request could not be sent.",
  not_found: LOST,
};

function refused(error: string): BackendRefusal {
  const message = REFUSALS[error] ?? error;

  return {
    ok: false,
    error: message,
  };
}

function stateOf<T>(job: BackendJob): JobState<T> {
  const { status, result, error } = job;

  if (status === "done") {
    return {
      status,
      result: result as T,
    };
  }

  if (status === "failed") {
    const message = error ?? LOST;

    return {
      status,
      error: message,
    };
  }

  return { status };
}

export function toJobRef(reply: BackendReply): ActionResult<JobRef> {
  if (!reply.ok) {
    return refused(reply.error);
  }

  const data: JobRef = {
    jobId: reply.job.job_id,
    kind: reply.job.kind,
  };

  return {
    ok: true,
    data,
  };
}

export function toJobState<T>(reply: BackendReply): ActionResult<JobState<T>> {
  if (!reply.ok && reply.error === "not_found") {
    return {
      ok: true,
      data: {
        status: "failed",
        error: LOST,
      },
    };
  }

  if (!reply.ok) {
    return refused(reply.error);
  }

  const data = stateOf<T>(reply.job);

  return {
    ok: true,
    data,
  };
}
