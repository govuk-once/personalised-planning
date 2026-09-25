"use server";

import { chatInput, planInput, type ChatInput, type PlanInput } from "@/lib/action-input";
import { BACKEND_URL, callBackend, describeFailure } from "@/lib/backend-client";
import { planTicket } from "@/lib/plan-ticket";
import type { ActionResult, ChatTurn, PlanRequest } from "@/lib/types";

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

  const { sessionId, messages, collectedFacts, lifeEventIds } = parsed.data;
  const userContext = {
    ...(collectedFacts ?? {}),
    ...(lifeEventIds?.length ? { life_event_ids: lifeEventIds } : {}),
  };
  return attempt(() =>
    callBackend<ChatTurn>("/chat", sessionId, {
      messages,
      user_context: Object.keys(userContext).length > 0 ? userContext : null,
    })
  );
}

export async function createPlanRequest(input: PlanInput): Promise<ActionResult<PlanRequest>> {
  const parsed = planInput.safeParse(input);
  if (!parsed.success) return rejected("That plan request could not be sent.");

  const { sessionId, situation, userContext } = parsed.data;
  const ticket = planTicket(sessionId);

  if (MOCK_MODE) {
    return { ok: true, data: { url: `${BACKEND_URL}/mock`, ticket, body: null } };
  }

  return {
    ok: true,
    data: {
      url: `${BACKEND_URL}/plan`,
      ticket,
      body: { situation, user_context: userContext ?? null },
    },
  };
}
