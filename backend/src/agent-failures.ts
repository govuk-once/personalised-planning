import type { Agent } from "./config.ts";
import { describeError, hasName, isAwsServiceError } from "./errors.ts";
import { TOO_LONG } from "./jobs.ts";

export const UNAVAILABLE =
  "The service is temporarily unavailable. Please try again shortly.";

// The message is shown to the user; the detail only goes to the logs.
export class AgentFailure extends Error {
  readonly detail: Record<string, unknown>;

  constructor(message: string, detail: Record<string, unknown>) {
    super(message);
    this.name = "AgentFailure";
    this.detail = detail;
  }
}

export class AgentHttpError extends Error {
  constructor(status: number) {
    super(`HTTP ${status}`);
    this.name = "AgentHttpError";
  }
}

function timedOut(error: unknown): boolean {
  const timeout = hasName(error, "TimeoutError");
  const aborted = hasName(error, "AbortError");

  return timeout || aborted;
}

function unreachable(error: unknown): boolean {
  if (!(error instanceof TypeError)) {
    return false;
  }

  return error.message === "fetch failed";
}

function messageFor(agent: Agent, error: unknown): string {
  if (timedOut(error)) {
    return TOO_LONG;
  }

  if (error instanceof AgentHttpError) {
    return `The ${agent.name} is temporarily unavailable.`;
  }

  if (unreachable(error)) {
    return `Unable to reach the ${agent.name}. Please try again.`;
  }

  return UNAVAILABLE;
}

export function failureFor(agent: Agent, error: unknown): AgentFailure {
  const { name, message } = describeError(error);

  const detail: Record<string, unknown> = {
    error_type: name,
    error: message,
  };

  if (isAwsServiceError(error)) {
    detail.error_code = name;
  }

  const shown = messageFor(agent, error);

  return new AgentFailure(shown, detail);
}
