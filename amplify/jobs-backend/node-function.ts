import { fileURLToPath } from "node:url";

import { Duration, RemovalPolicy } from "aws-cdk-lib";
import * as iam from "aws-cdk-lib/aws-iam";
import * as lambda from "aws-cdk-lib/aws-lambda";
import { NodejsFunction, OutputFormat } from "aws-cdk-lib/aws-lambda-nodejs";
import * as logs from "aws-cdk-lib/aws-logs";
import { Construct } from "constructs";

const BACKEND_URL = new URL("../../backend", import.meta.url);
const BACKEND = fileURLToPath(BACKEND_URL);

// Bundled CommonJS AWS SDK packages still call require() inside the ES module.
const REQUIRE_SHIM =
  "import { createRequire } from 'node:module'; const require = createRequire(import.meta.url);";

type AsyncSettings = {
  retryAttempts: number;
  maxEventAge: Duration;
  reservedConcurrency: number;
};

export type NodeFunctionProps = {
  entry: string;
  timeout: Duration;
  environment: Record<string, string>;
  async?: AsyncSettings;
};

export type NodeFunction = {
  fn: lambda.Function;
  role: iam.Role;
  logGroup: logs.LogGroup;
};

function logGroupFor(scope: Construct, id: string): logs.LogGroup {
  return new logs.LogGroup(scope, `${id}Logs`, {
    retention: logs.RetentionDays.ONE_YEAR,
    removalPolicy: RemovalPolicy.DESTROY,
  });
}

function roleFor(scope: Construct, id: string): iam.Role {
  const principal = new iam.ServicePrincipal("lambda.amazonaws.com");

  return new iam.Role(scope, `${id}Role`, {
    assumedBy: principal,
    description: `Runs the ${id} Lambda: its log group and nothing else unless granted`,
  });
}

export function nodeFunction(
  scope: Construct,
  id: string,
  props: NodeFunctionProps
): NodeFunction {
  const logGroup = logGroupFor(scope, id);
  const role = roleFor(scope, id);

  logGroup.grantWrite(role);

  const fn = new NodejsFunction(scope, id, {
    entry: `${BACKEND}/src/${props.entry}`,
    handler: "handler",
    projectRoot: BACKEND,
    depsLockFilePath: `${BACKEND}/package-lock.json`,
    runtime: lambda.Runtime.NODEJS_24_X,
    architecture: lambda.Architecture.ARM_64,
    timeout: props.timeout,
    memorySize: 512,
    role,
    logGroup,
    environment: props.environment,
    bundling: {
      format: OutputFormat.ESM,
      target: "node24",
      bundleAwsSDK: true,
      minify: false,
      sourceMap: false,
      banner: REQUIRE_SHIM,
    },
    retryAttempts: props.async?.retryAttempts,
    maxEventAge: props.async?.maxEventAge,
    reservedConcurrentExecutions: props.async?.reservedConcurrency,
  });

  return {
    fn,
    role,
    logGroup,
  };
}
