import type { InvokeAgent } from "./agents.ts";
import type { Settings } from "./config.ts";
import mockPlan from "./mock-plan.json" with { type: "json" };
import { chatTurn, planResult, type Shaped, withToday } from "./outputs.ts";
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

async function chat(request: ChatRequest, call: AgentCall): Promise<Shaped> {
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

  return chatTurn(reply);
}

async function plan(request: PlanRequest, call: AgentCall): Promise<Shaped> {
  if (request.mock) {
    return planResult(mockPlan);
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

  return planResult(reply);
}

export function askAgent(
  kind: Kind,
  request: AgentRequest,
  call: AgentCall
): Promise<Shaped> {
  if (kind === "chat") {
    return chat(request as ChatRequest, call);
  }

  return plan(request as PlanRequest, call);
}
