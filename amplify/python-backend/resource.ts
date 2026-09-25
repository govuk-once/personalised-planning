import { fileURLToPath } from "node:url";
import { Duration, RemovalPolicy, Tags } from "aws-cdk-lib";
import * as iam from "aws-cdk-lib/aws-iam";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as logs from "aws-cdk-lib/aws-logs";
import { Construct } from "constructs";

const BUNDLE_PATH = fileURLToPath(new URL(".build/lambda", import.meta.url));

function required(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is not set on this Amplify app`);
  return value;
}

export class PythonBackend extends Construct {
  readonly url: string;

  constructor(scope: Construct, id: string) {
    super(scope, id);

    const plannerArn = required("AGENT_RUNTIME_ARN");
    const chatArn = required("CHAT_AGENT_RUNTIME_ARN");

    const handler = new lambda.Function(this, "Handler", {
      runtime: lambda.Runtime.PYTHON_3_12,
      architecture: lambda.Architecture.ARM_64,
      handler: "handler.handler",
      code: lambda.Code.fromAsset(BUNDLE_PATH),
      timeout: Duration.seconds(300),
      memorySize: 1024,
      logGroup: new logs.LogGroup(this, "Logs", {
        retention: logs.RetentionDays.ONE_WEEK,
        removalPolicy: RemovalPolicy.DESTROY,
      }),
      environment: {
        LOCAL_MODE: "false",
        BACKEND_API_KEY: required("BACKEND_API_KEY"),
        AGENT_RUNTIME_ARN: plannerArn,
        AGENT_ENDPOINT_NAME: process.env.AGENT_ENDPOINT_NAME ?? "DEFAULT",
        CHAT_AGENT_RUNTIME_ARN: chatArn,
        CHAT_AGENT_ENDPOINT_NAME: process.env.CHAT_AGENT_ENDPOINT_NAME ?? "DEFAULT",
      },
    });

    handler.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ["bedrock-agentcore:InvokeAgentRuntime"],
        resources: [plannerArn, `${plannerArn}/*`, chatArn, `${chatArn}/*`],
      })
    );

    Tags.of(handler).add("pp:component", "backend");
    Tags.of(handler).add("pp:branch", process.env.AWS_BRANCH ?? "unknown");

    this.url = handler.addFunctionUrl({
      authType: lambda.FunctionUrlAuthType.NONE,
      cors: {
        allowedOrigins: ["*"],
        allowedMethods: [lambda.HttpMethod.GET, lambda.HttpMethod.POST],
        allowedHeaders: ["content-type", "x-session-id", "x-plan-ticket"],
        maxAge: Duration.hours(1),
      },
    }).url;
  }
}
