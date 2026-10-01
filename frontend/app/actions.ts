"use server";

import { planInput, ticketInput, type PlanInput, type TicketInput } from "@/lib/action-input";
import { planTicket } from "@/lib/plan-ticket";
import type { ActionResult, BackendRequest } from "@/lib/types";

const BACKEND_URL = (process.env.BACKEND_URL ?? "http://localhost:8000").replace(/\/+$/, "");
const MOCK_MODE = process.env.MOCK_MODE === "true";

const rejected = <T>(error: string): ActionResult<T> => ({ ok: false, error });

export async function createChatRequest(input: TicketInput): Promise<ActionResult<BackendRequest>> {
  const parsed = ticketInput.safeParse(input);
  if (!parsed.success) return rejected("That conversation could not be sent.");

  return {
    ok: true,
    data: { url: `${BACKEND_URL}/chat`, ticket: planTicket(parsed.data.sessionId), body: null },
  };
}

export async function createPlanRequest(input: PlanInput): Promise<ActionResult<BackendRequest>> {
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
