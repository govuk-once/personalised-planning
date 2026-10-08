import { type Parsed, parsed } from "./parsing.ts";
import type { AgentRequest, Kind } from "./requests.ts";
import { startChat, startPlan } from "./start-events.ts";
import { type Fields, isJobId, isRecord, isSessionId } from "./value-checks.ts";

export type StartJob = {
  action: "start";
  sessionId: string;
  kind: Kind;
  jobId: string | null;
  request: AgentRequest;
};

export type GetJob = {
  action: "get_job";
  sessionId: string;
  jobId: string;
};

export type ApiEvent = StartJob | GetJob;

function getJob(event: Fields): Parsed<ApiEvent> {
  const checks = {
    session_id: isSessionId(event.session_id),
    job_id: isJobId(event.job_id),
  };

  return parsed(checks, () => ({
    action: "get_job",
    sessionId: event.session_id as string,
    jobId: event.job_id as string,
  }));
}

const PARSERS = new Map<unknown, (event: Fields) => Parsed<ApiEvent>>([
  ["start_chat", startChat],
  ["start_plan", startPlan],
  ["get_job", getJob],
]);

export function parseApiEvent(event: unknown): Parsed<ApiEvent> {
  if (!isRecord(event)) {
    return {
      ok: false,
      problems: ["event"],
    };
  }

  const parser = PARSERS.get(event.action);

  if (!parser) {
    return {
      ok: false,
      problems: ["action"],
    };
  }

  return parser(event);
}
