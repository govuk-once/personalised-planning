export type Agent = {
  name: string;
  url: string;
  runtimeArn: string | undefined;
  qualifier: string;
};

export type Settings = {
  region: string;
  jobsTable: string;
  workerFunction: string;
  localAgents: boolean;
  chat: Agent;
  planner: Agent;
};

export type Env = Record<string, string | undefined>;

function agent(
  name: string,
  url: string,
  runtimeArn?: string,
  qualifier?: string
): Agent {
  return {
    name,
    url,
    runtimeArn: runtimeArn || undefined,
    qualifier: qualifier || "DEFAULT",
  };
}

export function settingsFrom(env: Env): Settings {
  const localMode = env.LOCAL_MODE?.toLowerCase();

  const chatUrl = env.CHAT_AGENT_URL || "http://localhost:8081/invocations";
  const plannerUrl = env.AGENT_URL || "http://localhost:8080/invocations";

  const chat = agent(
    "chat agent",
    chatUrl,
    env.CHAT_AGENT_RUNTIME_ARN,
    env.CHAT_AGENT_ENDPOINT_NAME
  );

  const planner = agent(
    "planner agent",
    plannerUrl,
    env.AGENT_RUNTIME_ARN,
    env.AGENT_ENDPOINT_NAME
  );

  return {
    region: env.AWS_REGION || env.AWS_DEFAULT_REGION || "eu-west-2",
    jobsTable: env.JOBS_TABLE || "pp-jobs-local",
    workerFunction: env.WORKER_FUNCTION_NAME || "pp-worker",
    localAgents: localMode === "true",
    chat,
    planner,
  };
}
