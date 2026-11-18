import type { BedrockAgentCoreClient } from "@aws-sdk/client-bedrock-agentcore";

type AgentCall = {
  runtimeSessionId?: string;
  baggage?: string;
};

// Baggage puts the session id on agent spans
export function withSessionBaggage(
  client: BedrockAgentCoreClient
): BedrockAgentCoreClient {
  client.middlewareStack.add(
    next => args => {
      const call = args.input as AgentCall;

      if (call.runtimeSessionId) {
        call.baggage ??= `session.id=${call.runtimeSessionId}`;
      }

      return next(args);
    },
    {
      step: "initialize",
      name: "sessionBaggage",
    }
  );

  return client;
}
