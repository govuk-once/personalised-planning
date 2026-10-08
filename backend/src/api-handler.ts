import { randomUUID } from "node:crypto";

import { InvokeCommand } from "@aws-sdk/client-lambda";

import { type ApiDeps, handle, type WorkerPayload } from "./api.ts";
import { dynamoDb, lambda } from "./clients.ts";
import { settingsFrom } from "./config.ts";
import { stdout } from "./log.ts";
import { createStore } from "./store.ts";

const settings = settingsFrom(process.env);
const lambdaClient = lambda(settings.region);

async function startWorker(payload: WorkerPayload): Promise<void> {
  const text = JSON.stringify(payload);
  const bytes = new TextEncoder().encode(text);

  const command = new InvokeCommand({
    FunctionName: settings.workerFunction,
    InvocationType: "Event",
    Payload: bytes,
  });

  await lambdaClient.send(command);
}

function newId(): string {
  return randomUUID().replaceAll("-", "");
}

const dynamoDbClient = dynamoDb(settings.region);
const store = createStore(dynamoDbClient, settings.jobsTable);

const deps: ApiDeps = {
  store,
  startWorker,
  nowMs: Date.now,
  newId,
  log: stdout,
};

export const handler = (event: unknown) => handle(event, deps);
