import { agentRuntimes } from "../jobs-backend/agent-access";
import type { Branch } from "../jobs-backend/branch-settings";
import { endpointName } from "../jobs-backend/functions";

const SERVICE_GRAPH_LOGS = "/aws/lambda/govuk-service-graph-mcp";
const CLAUDE_CALL_LOGS = "bedrock-model-invocation-logs";
const TEAM_MONITOR = "personalised-planning-browser-monitoring";

const UNSAFE_CHARACTER = /[^A-Za-z0-9_-]/gu;
const LONGEST_TRACE_GROUP = 32;

export type Monitor = {
  name: string;
  logGroup: string;
};

export type Site = {
  name: string;
  traceGroup: string;
  monitor: Monitor | null;
  websiteLogs: string;
  conversationLogs: string;
  plannerLogs: string;
  serviceGraphLogs: string;
  claudeCallLogs: string;
};

function nameSafe(text: string): string {
  return text.replaceAll(UNSAFE_CHARACTER, "-");
}

function runtimeLogs(arn: string, endpointVariable: string): string {
  const runtimeId = arn.split("/").at(-1);
  const endpoint = endpointName(endpointVariable);

  return `/aws/bedrock-agentcore/runtimes/${runtimeId}-${endpoint}`;
}

function browserMonitor(): Monitor | null {
  const id = process.env.NEXT_PUBLIC_RUM_APP_MONITOR_ID;

  if (!id) {
    return null;
  }

  const name = process.env.RUM_APP_MONITOR_NAME ?? TEAM_MONITOR;
  const idStart = id.slice(0, 8);

  return {
    name,
    logGroup: `/aws/vendedlogs/RUMService_${name}${idStart}`,
  };
}

export function siteOf(branch: Branch): Site {
  const agents = agentRuntimes();
  const branchName = nameSafe(branch.name);
  const name = `personalised-planning-${branchName}`;

  return {
    name,
    traceGroup: name.slice(0, LONGEST_TRACE_GROUP),
    monitor: browserMonitor(),
    websiteLogs: `/aws/amplify/${branch.appId}`,
    conversationLogs: runtimeLogs(agents.chat, "CHAT_AGENT_ENDPOINT_NAME"),
    plannerLogs: runtimeLogs(agents.planner, "AGENT_ENDPOINT_NAME"),
    serviceGraphLogs: SERVICE_GRAPH_LOGS,
    claudeCallLogs: CLAUDE_CALL_LOGS,
  };
}
