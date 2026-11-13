import type * as lambda from "aws-cdk-lib/aws-lambda";
import * as xray from "aws-cdk-lib/aws-xray";
import type { Construct } from "constructs";

export function traceGroup(
  scope: Construct,
  name: string,
  api: lambda.IFunction
): xray.CfnGroup {
  return new xray.CfnGroup(scope, "TraceGroup", {
    groupName: name,
    filterExpression: `service("${api.functionName}")`,
    insightsConfiguration: {
      insightsEnabled: false,
      notificationsEnabled: false,
    },
  });
}
