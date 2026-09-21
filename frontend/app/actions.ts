"use server";

import { chatInput, planInput, type ChatInput, type PlanInput } from "@/lib/action-input";
import { callBackend, describeFailure } from "@/lib/backend-client";
import type { ActionResult, ChatTurn, PlanResult } from "@/lib/types";

const MOCK_MODE = process.env.MOCK_MODE === "true";

const rejected = <T>(error: string): ActionResult<T> => ({ ok: false, error });

async function attempt<T>(call: () => Promise<T>): Promise<ActionResult<T>> {
  try {
    return { ok: true, data: await call() };
  } catch (error) {
    return { ok: false, error: describeFailure(error) };
  }
}

export async function sendChatTurn(input: ChatInput): Promise<ActionResult<ChatTurn>> {
  const parsed = chatInput.safeParse(input);
  if (!parsed.success) return rejected("That conversation could not be sent.");

  const { sessionId, messages, collectedFacts } = parsed.data;
  return attempt(() =>
    callBackend<ChatTurn>("/chat", sessionId, {
      messages,
      user_context: collectedFacts ?? null,
    })
  );
}

export async function createPlan(input: PlanInput): Promise<ActionResult<PlanResult>> {
  const parsed = planInput.safeParse(input);
  if (!parsed.success) return rejected("That plan request could not be sent.");

  const { sessionId, situation, userContext } = parsed.data;
  return attempt(() =>
    MOCK_MODE
      ? callBackend<PlanResult>("/mock", sessionId)
      : callBackend<PlanResult>("/plan", sessionId, {
          situation,
          user_context: userContext ?? null,
        })
  );
}
