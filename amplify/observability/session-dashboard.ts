import { Duration, Stack } from "aws-cdk-lib";
import * as cloudwatch from "aws-cdk-lib/aws-cloudwatch";
import type { Construct } from "constructs";

import * as queries from "./session-queries";
import { browserTable, links, table } from "./session-widgets";
import type { Site } from "./site";

const SPANS = "aws/spans";

export type BackendLogs = {
  api: string;
  worker: string;
};

function widgets(
  scope: Construct,
  site: Site,
  backend: BackendLogs
): cloudwatch.IWidget[][] {
  const { account, region } = Stack.of(scope);
  const jobLogs = [backend.api, backend.worker];
  const turnLogs = [site.websiteLogs, ...jobLogs];
  const agentLogs = [site.conversationLogs, site.plannerLogs];
  const everyPart = [...turnLogs, ...agentLogs, site.serviceGraphLogs];

  const turns = table({
    title: "Turns",
    logGroups: turnLogs,
    query: queries.turnsQuery(),
    height: 10,
  });
  const dynamoDb = table({
    title: "DynamoDB",
    logGroups: jobLogs,
    query: queries.dynamoDbQuery(),
    height: 8,
  });
  const errors = table({
    title: "Errors",
    logGroups: everyPart,
    query: queries.problemsQuery(account),
    height: 4,
  });
  const agentSteps = table({
    title: "Agent timing",
    logGroups: [SPANS, ...agentLogs],
    query: queries.agentStepsQuery(),
    height: 6,
  });
  const claudeCalls = table({
    title: "Claude calls",
    logGroups: [site.claudeCallLogs],
    query: queries.claudeCallsQuery(),
    height: 8,
  });

  return [
    [links(region, site)],
    [turns],
    browserTable(site),
    [dynamoDb],
    [errors],
    [agentSteps],
    [claudeCalls],
  ];
}

export function sessionDashboard(
  scope: Construct,
  site: Site,
  backend: BackendLogs
): cloudwatch.Dashboard {
  const session = new cloudwatch.DashboardVariable({
    id: "session",
    label: "Session id",
    type: cloudwatch.VariableType.PATTERN,
    inputType: cloudwatch.VariableInputType.INPUT,
    value: queries.SESSION,
    defaultValue: cloudwatch.DefaultValue.value(queries.SESSION),
  });

  return new cloudwatch.Dashboard(scope, "Sessions", {
    dashboardName: `${site.name}-sessions`,
    defaultInterval: Duration.hours(12),
    variables: [session],
    widgets: widgets(scope, site, backend),
  });
}
