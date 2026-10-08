import {
  type BedrockAgentCoreClient,
  InvokeAgentRuntimeCommand,
} from "@aws-sdk/client-bedrock-agentcore";

import {
  AgentFailure,
  AgentHttpError,
  failureFor,
  UNAVAILABLE,
} from "./agent-failures.ts";
import type { Agent, Settings } from "./config.ts";

export type InvokeAgent = (
  agent: Agent,
  sessionId: string,
  payload: unknown,
  timeoutMs: number
) => Promise<unknown>;

function jsonBody(payload: unknown): Uint8Array {
  const text = JSON.stringify(payload);

  return new TextEncoder().encode(text);
}

async function overHttp(
  agent: Agent,
  payload: unknown,
  timeoutMs: number
): Promise<unknown> {
  const body = JSON.stringify(payload);
  const signal = AbortSignal.timeout(timeoutMs);

  const response = await fetch(agent.url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body,
    signal,
  });

  if (!response.ok) {
    throw new AgentHttpError(response.status);
  }

  return response.json();
}

async function overAgentCore(
  client: BedrockAgentCoreClient,
  agent: Agent,
  sessionId: string,
  payload: unknown,
  timeoutMs: number
): Promise<unknown> {
  if (!agent.runtimeArn) {
    const error = `no runtime ARN for the ${agent.name}`;

    throw new AgentFailure(UNAVAILABLE, { error });
  }

  const body = jsonBody(payload);

  const command = new InvokeAgentRuntimeCommand({
    agentRuntimeArn: agent.runtimeArn,
    runtimeSessionId: sessionId,
    qualifier: agent.qualifier,
    contentType: "application/json",
    accept: "application/json",
    payload: body,
  });

  const abortSignal = AbortSignal.timeout(timeoutMs);
  const reply = await client.send(command, { abortSignal });
  const text = await reply.response?.transformToString();
  const json = text ?? "null";

  return JSON.parse(json);
}

export function agentInvoker(
  settings: Settings,
  client: BedrockAgentCoreClient
): InvokeAgent {
  return async (agent, sessionId, payload, timeoutMs) => {
    try {
      if (settings.localAgents) {
        return await overHttp(agent, payload, timeoutMs);
      }

      return await overAgentCore(client, agent, sessionId, payload, timeoutMs);
    } catch (error) {
      if (error instanceof AgentFailure) {
        throw error;
      }

      throw failureFor(agent, error);
    }
  };
}
