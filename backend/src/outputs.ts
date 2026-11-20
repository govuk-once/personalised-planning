import type { ChatTurn } from "./chat-reply.ts";
import type { Context, Kind } from "./requests.ts";
import { outputOf, recordOrNull } from "./reply-fields.ts";
import {
  chatProblem,
  chatSummary,
  planProblem,
  planSummary,
} from "./shape-checks.ts";

export { chatTurn, type ChatTurn } from "./chat-reply.ts";

export type PlanResult = {
  plan: Record<string, unknown> | null;
  agent_help: unknown;
};

export type Shaped = ChatTurn | PlanResult;

const LONG_DATE = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "long",
  year: "numeric",
  timeZone: "Europe/London",
});

// Without a date the planner works out deadlines from its training cutoff.
export function withToday(
  userContext: Context,
  now: Date
): Record<string, unknown> {
  const today = LONG_DATE.format(now);

  return {
    today,
    ...userContext,
  };
}

export function planResult(reply: unknown): PlanResult {
  const output = outputOf(reply);

  return {
    plan: recordOrNull(output.plan),
    agent_help: output.agent_help ?? null,
  };
}

export function shapeProblem(kind: Kind, shaped: Shaped): string | null {
  if (kind === "chat") {
    return chatProblem(shaped as ChatTurn);
  }

  if (kind === "plan") {
    return planProblem(shaped as PlanResult);
  }

  return null;
}

export function summaryOf(kind: Kind, shaped: Shaped): Record<string, unknown> {
  if (kind === "chat") {
    return chatSummary(shaped as ChatTurn);
  }

  return planSummary(shaped as PlanResult);
}
