import type { InvokeAgent } from "./agents.ts";
import type { Settings } from "./config.ts";
import mockPlan from "./mock-plan.json" with { type: "json" };
import { offerLogFields } from "./answer-helpers.ts";
import { chatReply } from "./chat-reply.ts";
import { planResult, type Shaped, withToday } from "./outputs.ts";
import type {
  AgentRequest,
  ChatRequest,
  Kind,
  PlanRequest,
} from "./requests.ts";

export type AgentCall = {
  settings: Settings;
  invokeAgent: InvokeAgent;
  sessionId: string;
  now: Date;
  timeoutMs: number;
};

export type Answer = {
  shaped: Shaped;
  logFields: Record<string, unknown>;
};

function withoutLogFields(shaped: Shaped): Answer {
  return {
    shaped,
    logFields: {},
  };
}

async function chat(request: ChatRequest, call: AgentCall): Promise<Answer> {
  const userContext = withToday(request.user_context, call.now);

  const payload = {
    session_id: call.sessionId,
    messages: request.messages,
    user_context: userContext,
  };

  const reply = await call.invokeAgent(
    call.settings.chat,
    call.sessionId,
    payload,
    call.timeoutMs
  );

  const { turn, offer } = chatReply(reply, call.settings.quickReplies);
  const logFields = offerLogFields(offer);

  return {
    shaped: turn,
    logFields,
  };
}

async function plan(request: PlanRequest, call: AgentCall): Promise<Answer> {
  if (request.mock) {
    const mock = planResult(mockPlan);

    return withoutLogFields(mock);
  }

  const userContext = withToday(request.user_context, call.now);

  const payload = {
    session_id: call.sessionId,
    situation: request.situation,
    user_context: userContext,
  };

  const reply = await call.invokeAgent(
    call.settings.planner,
    call.sessionId,
    payload,
    call.timeoutMs
  );

  const result = planResult(reply);

  return withoutLogFields(result);
}

export function askAgent(
  kind: Kind,
  request: AgentRequest,
  call: AgentCall
): Promise<Answer> {
  if (kind === "chat") {
    return chat(request as ChatRequest, call);
  }

  return plan(request as PlanRequest, call);
}
