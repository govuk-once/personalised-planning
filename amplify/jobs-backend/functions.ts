import { Duration } from "aws-cdk-lib";
import type * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import { Construct } from "constructs";

import {
  MAX_EVENT_AGE_SECONDS,
  WORKER_TIMEOUT_SECONDS,
} from "../../backend/src/timing";
import { agentRuntimes, invokeAgents } from "./agent-access";
import { type NodeFunction, nodeFunction } from "./node-function";

const API_TABLE_ACTIONS = [
  "dynamodb:PutItem",
  "dynamodb:GetItem",
  "dynamodb:UpdateItem",
  "dynamodb:Query",
];

function endpointName(variable: string): string {
  return process.env[variable] ?? "DEFAULT";
}

export function workerFunction(
  scope: Construct,
  table: dynamodb.Table
): NodeFunction {
  const agents = agentRuntimes();
  const agentEndpoint = endpointName("AGENT_ENDPOINT_NAME");
  const chatEndpoint = endpointName("CHAT_AGENT_ENDPOINT_NAME");
  const timeout = Duration.seconds(WORKER_TIMEOUT_SECONDS);
  const maxEventAge = Duration.seconds(MAX_EVENT_AGE_SECONDS);

  const worker = nodeFunction(scope, "Worker", {
    entry: "worker-handler.ts",
    timeout,
    environment: {
      JOBS_TABLE: table.tableName,
      LOCAL_MODE: "false",
      AGENT_RUNTIME_ARN: agents.planner,
      AGENT_ENDPOINT_NAME: agentEndpoint,
      CHAT_AGENT_RUNTIME_ARN: agents.chat,
      CHAT_AGENT_ENDPOINT_NAME: chatEndpoint,
    },
    async: {
      retryAttempts: 0,
      maxEventAge,
      reservedConcurrency: 20,
    },
  });

  const invoke = invokeAgents([agents.planner, agents.chat]);

  worker.role.addToPolicy(invoke);
  table.grant(worker.role, "dynamodb:UpdateItem");

  return worker;
}

export function apiFunction(
  scope: Construct,
  table: dynamodb.Table,
  worker: NodeFunction
): NodeFunction {
  const timeout = Duration.seconds(15);

  const api = nodeFunction(scope, "Api", {
    entry: "api-handler.ts",
    timeout,
    environment: {
      JOBS_TABLE: table.tableName,
      WORKER_FUNCTION_NAME: worker.fn.functionName,
    },
  });

  table.grant(api.role, ...API_TABLE_ACTIONS);
  worker.fn.grantInvoke(api.role);

  return api;
}
