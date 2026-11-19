import type { AgentRequest } from "./requests.ts";

// Logs sizes only
export function requestSummary(request: AgentRequest) {
  const context = request.user_context ?? {};
  const facts = Object.keys(context).length;

  if ("situation" in request) {
    return {
      situation_chars: request.situation.length,
      facts,
    };
  }

  const latest = request.messages.at(-1);

  return {
    messages: request.messages.length,
    message_chars: latest?.content.length,
    facts,
  };
}
