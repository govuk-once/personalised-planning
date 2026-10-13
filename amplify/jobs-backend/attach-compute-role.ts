import { Stack } from "aws-cdk-lib";
import * as iam from "aws-cdk-lib/aws-iam";
import type * as logs from "aws-cdk-lib/aws-logs";
import {
  AwsCustomResource,
  AwsCustomResourcePolicy,
  PhysicalResourceId,
} from "aws-cdk-lib/custom-resources";
import { Construct } from "constructs";

import type { Branch } from "./branch-settings";

function branchArn(scope: Construct, branch: Branch): string {
  const { region, account } = Stack.of(scope);

  return `arn:aws:amplify:${region}:${account}:apps/${branch.appId}/branches/${branch.name}`;
}

export function attachComputeRole(
  scope: Construct,
  branch: Branch,
  role: iam.Role,
  logGroup: logs.LogGroup
): void {
  const passRole = new iam.PolicyStatement({
    actions: ["iam:PassRole"],
    resources: [role.roleArn],
  });

  const updateBranch = new iam.PolicyStatement({
    actions: ["amplify:UpdateBranch"],
    resources: [branchArn(scope, branch)],
  });

  new AwsCustomResource(scope, "AttachComputeRole", {
    onUpdate: {
      service: "Amplify",
      action: "updateBranch",
      parameters: {
        appId: branch.appId,
        branchName: branch.name,
        computeRoleArn: role.roleArn,
      },
      physicalResourceId: PhysicalResourceId.of(`${branch.name}-compute-role`),
    },
    onDelete: {
      service: "Amplify",
      action: "updateBranch",
      parameters: {
        appId: branch.appId,
        branchName: branch.name,
        computeRoleArn: "",
      },
      // The branch may already be gone when its stack is deleted.
      ignoreErrorCodesMatching: "NotFoundException",
    },
    policy: AwsCustomResourcePolicy.fromStatements([passRole, updateBranch]),
    logGroup,
    installLatestAwsSdk: false,
  });
}
