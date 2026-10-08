type Env = Record<string, string | undefined>;

const PLACEHOLDER_ARN =
  "arn:aws:bedrock-agentcore:eu-west-2:000000000000:runtime/local-agents";

function fromContainer(port: number): string {
  return `http://host.docker.internal:${port}`;
}

function invocationsOn(port: number): string {
  const origin = fromContainer(port);

  return `${origin}/invocations`;
}

function endpoints(env: Env): Record<string, string> {
  const dynamodb = env.LOCAL_DYNAMODB_URL ?? fromContainer(8001);
  // The Worker's own SAM endpoint, without warm containers, so jobs run side by side.
  const lambda = env.LOCAL_LAMBDA_URL ?? fromContainer(8002);

  return {
    AWS_ENDPOINT_URL_DYNAMODB: dynamodb,
    AWS_ENDPOINT_URL_LAMBDA: lambda,
  };
}

function localAgents(env: Env): Record<string, string> {
  const planner = env.AGENT_URL ?? invocationsOn(8080);
  const chat = env.CHAT_AGENT_URL ?? invocationsOn(8081);

  return {
    LOCAL_MODE: "true",
    AGENT_URL: planner,
    CHAT_AGENT_URL: chat,
  };
}

export function localEnvironment(env: Env): Record<string, string> {
  const services = endpoints(env);

  if (env.LOCAL_MODE !== "true") {
    return services;
  }

  const agents = localAgents(env);

  return {
    ...services,
    ...agents,
  };
}

export function useLocalAgentPlaceholders(env: Env): void {
  if (env.LOCAL_MODE !== "true") {
    return;
  }

  env.AGENT_RUNTIME_ARN ??= PLACEHOLDER_ARN;
  env.CHAT_AGENT_RUNTIME_ARN ??= PLACEHOLDER_ARN;
}
