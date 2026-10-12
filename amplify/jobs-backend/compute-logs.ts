import { Stack } from "aws-cdk-lib";
import * as iam from "aws-cdk-lib/aws-iam";
import * as logs from "aws-cdk-lib/aws-logs";
import {
  AwsCustomResource,
  AwsCustomResourcePolicy,
  PhysicalResourceId,
} from "aws-cdk-lib/custom-resources";
import { Construct } from "constructs";

import type { Branch } from "./branch-settings";

// Amplify creates the Next.js log group itself, with no retention.
export function keepComputeLogs(
  scope: Construct,
  branch: Branch,
  logGroup: logs.LogGroup
): void {
  const logGroupName = `/aws/amplify/${branch.appId}`;
  const { region, account } = Stack.of(scope);
  const groupArn = `arn:aws:logs:${region}:${account}:log-group:${logGroupName}`;

  const manageGroup = new iam.PolicyStatement({
    actions: ["logs:CreateLogGroup", "logs:PutRetentionPolicy"],
    resources: [groupArn, `${groupArn}:*`],
  });

  const created = new AwsCustomResource(scope, "ComputeLogGroup", {
    onUpdate: {
      service: "CloudWatchLogs",
      action: "createLogGroup",
      parameters: { logGroupName },
      physicalResourceId: PhysicalResourceId.of(logGroupName),
      ignoreErrorCodesMatching: "ResourceAlreadyExistsException",
    },
    policy: AwsCustomResourcePolicy.fromStatements([manageGroup]),
    logGroup,
    installLatestAwsSdk: false,
  });

  const retention = new AwsCustomResource(scope, "ComputeLogRetention", {
    onUpdate: {
      service: "CloudWatchLogs",
      action: "putRetentionPolicy",
      parameters: {
        logGroupName,
        retentionInDays: logs.RetentionDays.ONE_YEAR,
      },
      physicalResourceId: PhysicalResourceId.of(`${logGroupName}-retention`),
    },
    policy: AwsCustomResourcePolicy.fromStatements([manageGroup]),
    logGroup,
    installLatestAwsSdk: false,
  });

  retention.node.addDependency(created);
}
