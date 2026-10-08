import { type Parsed, parsed } from "./parsing.ts";
import type { AgentRequest, Kind } from "./requests.ts";
import { isJobId, isRecord, isSessionId } from "./value-checks.ts";

export type WorkerEvent = {
  sessionId: string;
  jobId: string;
  kind: Kind;
  request: AgentRequest;
};

// The Api has already validated the request itself.
export function parseWorkerEvent(event: unknown): Parsed<WorkerEvent> {
  if (!isRecord(event)) {
    return {
      ok: false,
      problems: ["event"],
    };
  }

  const checks = {
    session_id: isSessionId(event.session_id),
    job_id: isJobId(event.job_id),
    kind: event.kind === "chat" || event.kind === "plan",
    request: isRecord(event.request),
  };

  return parsed(checks, () => ({
    sessionId: event.session_id as string,
    jobId: event.job_id as string,
    kind: event.kind as Kind,
    request: event.request as AgentRequest,
  }));
}
