import * as iam from "aws-cdk-lib/aws-iam";

export function required(name: string): string {
  const value = process.env[name];

  if (!value) {
    throw new Error(`${name} is not set on this Amplify app`);
  }

  return value;
}

export function agentRuntimes() {
  const planner = required("AGENT_RUNTIME_ARN");
  const chat = required("CHAT_AGENT_RUNTIME_ARN");

  return {
    planner,
    chat,
  };
}

export function invokeAgents(arns: string[]): iam.PolicyStatement {
  const resources = arns.flatMap(arn => [arn, `${arn}/*`]);

  return new iam.PolicyStatement({
    actions: ["bedrock-agentcore:InvokeAgentRuntime"],
    resources,
  });
}
