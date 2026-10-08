import type { ChatTurn, PlanResult } from "./outputs.ts";
import { listOrEmpty } from "./reply-fields.ts";

export function chatProblem(turn: ChatTurn): string | null {
  const message = turn.message.trim();

  if (!message) {
    return "The adviser did not reply. Please try again.";
  }

  return null;
}

export function planProblem(result: PlanResult): string | null {
  if (!result.plan) {
    return "The planner did not return a plan. Try starting again.";
  }

  return null;
}

export function chatSummary(turn: ChatTurn): Record<string, unknown> {
  const facts = Object.keys(turn.collected_facts);

  return {
    complete: turn.complete,
    facts: facts.length,
  };
}

export function planSummary(result: PlanResult): Record<string, unknown> {
  const steps = listOrEmpty(result.plan?.steps);

  return { steps: steps.length };
}
