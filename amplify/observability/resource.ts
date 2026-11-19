import { CfnOutput, Stack } from "aws-cdk-lib";
import type { Construct } from "constructs";

import { amplifyBranch } from "../jobs-backend/branch-settings";
import type { JobsBackend } from "../jobs-backend/resource";
import { dashboardUrl } from "./console-links";
import { sessionDashboard } from "./session-dashboard";
import { siteOf } from "./site";
import { traceGroup } from "./trace-group";

export function observeSessions(scope: Construct, jobs: JobsBackend): void {
  const branch = amplifyBranch();

  if (!branch) {
    return;
  }

  const site = siteOf(branch);
  const { region } = Stack.of(scope);

  traceGroup(scope, site.traceGroup, jobs.api.fn);

  const dashboard = sessionDashboard(scope, site, {
    api: jobs.api.logGroup.logGroupName,
    worker: jobs.worker.logGroup.logGroupName,
  });

  new CfnOutput(scope, "SessionDashboard", {
    value: dashboardUrl(region, dashboard.dashboardName),
  });
}
