import { randomUUID } from "node:crypto";

import { agentInvoker } from "./agents.ts";
import { agentCore, patientDynamoDb } from "./clients.ts";
import { settingsFrom } from "./config.ts";
import { stdout } from "./log.ts";
import { createStore } from "./store.ts";
import { handle, type WorkerDeps } from "./worker.ts";

// The agent call stops this long before Lambda would, so the job can still be marked failed.
const SAFETY_MARGIN_MS = 15_000;
const MINIMUM_TIMEOUT_MS = 1_000;

type LambdaContext = { getRemainingTimeInMillis(): number };

function newRunId(): string {
  return randomUUID().replaceAll("-", "");
}

const settings = settingsFrom(process.env);
const dynamoDbClient = patientDynamoDb(settings.region);
const store = createStore(dynamoDbClient, settings.jobsTable);
const agentCoreClient = agentCore(settings.region);
const invokeAgent = agentInvoker(settings, agentCoreClient);

const deps: WorkerDeps = {
  settings,
  store,
  invokeAgent,
  nowMs: Date.now,
  newRunId,
  log: stdout,
};

function agentTimeoutMs(context: LambdaContext): number {
  const remainingMs = context.getRemainingTimeInMillis();
  const timeoutMs = remainingMs - SAFETY_MARGIN_MS;

  return Math.max(timeoutMs, MINIMUM_TIMEOUT_MS);
}

export const handler = (event: unknown, context: LambdaContext) => {
  const timeoutMs = agentTimeoutMs(context);

  return handle(event, deps, timeoutMs);
};
