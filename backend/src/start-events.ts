import type { ApiEvent, StartJob } from "./events.ts";
import { isContext, isTranscript, LIMITS } from "./limits.ts";
import { type Parsed, parsed } from "./parsing.ts";
import type { Context, Kind, Message } from "./requests.ts";
import { type Fields, isJobId, isSessionId, isText } from "./value-checks.ts";

// The page may name the job, so that starting it again after a reload finds the same job.
function isOwnJobId(value: unknown, kind: Kind): boolean {
  if (value === undefined) {
    return true;
  }

  if (!isJobId(value)) {
    return false;
  }

  return value.startsWith(`${kind}-`);
}

function isOptionalBoolean(value: unknown): boolean {
  if (value === undefined) {
    return true;
  }

  return typeof value === "boolean";
}

function jobIdOf(event: Fields): string | null {
  return (event.job_id as string | undefined) ?? null;
}

function contextOf(event: Fields): Context {
  return (event.user_context ?? null) as Context;
}

function onlyRoleAndContent(messages: Message[]): Message[] {
  return messages.map(({ role, content }) => ({ role, content }));
}

function chatJob(event: Fields): StartJob {
  const messages = onlyRoleAndContent(event.messages as Message[]);

  return {
    action: "start",
    sessionId: event.session_id as string,
    kind: "chat",
    jobId: jobIdOf(event),
    request: {
      messages,
      user_context: contextOf(event),
    },
  };
}

function planJob(event: Fields): StartJob {
  return {
    action: "start",
    sessionId: event.session_id as string,
    kind: "plan",
    jobId: jobIdOf(event),
    request: {
      situation: event.situation as string,
      user_context: contextOf(event),
      mock: event.mock === true,
    },
  };
}

export function startChat(event: Fields): Parsed<ApiEvent> {
  const checks = {
    session_id: isSessionId(event.session_id),
    messages: isTranscript(event.messages),
    user_context: isContext(event.user_context),
    job_id: isOwnJobId(event.job_id, "chat"),
  };

  return parsed(checks, () => chatJob(event));
}

export function startPlan(event: Fields): Parsed<ApiEvent> {
  const checks = {
    session_id: isSessionId(event.session_id),
    situation: isText(event.situation, 1, LIMITS.situationChars),
    user_context: isContext(event.user_context),
    mock: isOptionalBoolean(event.mock),
    job_id: isOwnJobId(event.job_id, "plan"),
  };

  return parsed(checks, () => planJob(event));
}
