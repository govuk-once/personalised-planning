import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { App, Stack } from "aws-cdk-lib";
import type * as lambda from "aws-cdk-lib/aws-lambda";

import { JobsBackend } from "./jobs-backend/resource";
import {
  localEnvironment,
  useLocalAgentPlaceholders,
} from "./local/environment";
import { tableOf } from "./local/table";

const OUT = ".local";
const STACK = "PpLocal";
const CDK_OUT = join(OUT, "cdk.out");

function addLocalEnvironment(
  backend: JobsBackend,
  environment: Record<string, string>
): void {
  for (const fn of backend.functions) {
    for (const [name, value] of Object.entries(environment)) {
      fn.addEnvironment(name, value);
    }
  }
}

function logicalIdOf(stack: Stack, fn: lambda.Function): string {
  const resource = fn.node.defaultChild as lambda.CfnFunction;

  return stack.getLogicalId(resource);
}

useLocalAgentPlaceholders(process.env);

const app = new App({
  outdir: CDK_OUT,
  context: { "aws:cdk:enable-asset-metadata": true },
});
const stack = new Stack(app, STACK, { env: { region: "eu-west-2" } });
const backend = new JobsBackend(stack, "Backend");
const environment = localEnvironment(process.env);

addLocalEnvironment(backend, environment);

const assembly = app.synth();
const template = assembly.getStackByName(STACK).template;
const [api, worker] = backend.functions.map(fn => logicalIdOf(stack, fn));
const table = tableOf(template);
const templatePath = join(CDK_OUT, `${STACK}.template.json`);

const summary = {
  template: templatePath,
  apiFunction: api,
  workerFunction: worker,
  table,
};
const json = JSON.stringify(summary, null, 2);
const summaryPath = join(OUT, "backend.json");

mkdirSync(OUT, { recursive: true });
writeFileSync(summaryPath, `${json}\n`);

const tableName = table.definition.TableName;

console.log(
  `Synthesised ${templatePath}: Api ${api}, Worker ${worker}, table ${tableName}`
);
