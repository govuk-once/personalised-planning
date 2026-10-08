import { RemovalPolicy } from "aws-cdk-lib";
import type * as iam from "aws-cdk-lib/aws-iam";
import * as logs from "aws-cdk-lib/aws-logs";
import { Construct } from "constructs";

import { attachComputeRole } from "./attach-compute-role";
import { keepComputeLogs } from "./compute-logs";

export type Branch = {
  appId: string;
  name: string;
};

// Set by Amplify's build; a local synth or a sandbox has no branch to configure.
function amplifyBranch(): Branch | null {
  const appId = process.env.AWS_APP_ID;
  const name = process.env.AWS_BRANCH;

  if (!appId || !name) {
    return null;
  }

  return {
    appId,
    name,
  };
}

export function configureBranch(scope: Construct, role: iam.Role): void {
  const branch = amplifyBranch();

  if (!branch) {
    return;
  }

  const logGroup = new logs.LogGroup(scope, "BranchSettingsLogs", {
    retention: logs.RetentionDays.ONE_YEAR,
    removalPolicy: RemovalPolicy.DESTROY,
  });

  attachComputeRole(scope, branch, role, logGroup);
  keepComputeLogs(scope, branch, logGroup);
}
