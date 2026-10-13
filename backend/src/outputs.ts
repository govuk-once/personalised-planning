import type { Context, Kind } from "./requests.ts";
import {
  listOrEmpty,
  outputOf,
  recordOrEmpty,
  recordOrNull,
  textOrNull,
} from "./reply-fields.ts";
import {
  chatProblem,
  chatSummary,
  planProblem,
  planSummary,
} from "./shape-checks.ts";

export type ChatTurn = {
  message: string;
  life_event_ids: unknown[];
  collected_facts: Record<string, unknown>;
  outstanding: unknown[];
  complete: boolean;
  situation: string | null;
};

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

export function chatTurn(reply: unknown): ChatTurn {
  const output = outputOf(reply);
  const message = textOrNull(output.message) ?? "";

  return {
    message,
    life_event_ids: listOrEmpty(output.life_event_ids),
    collected_facts: recordOrEmpty(output.collected_facts),
    outstanding: listOrEmpty(output.outstanding),
    complete: output.complete === true,
    situation: textOrNull(output.situation),
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
