import { CfnOutput, Stack, Tags } from "aws-cdk-lib";
import type * as lambda from "aws-cdk-lib/aws-lambda";
import { Construct } from "constructs";

import { configureBranch } from "./branch-settings";
import { computeRole } from "./compute-role";
import { apiFunction, workerFunction } from "./functions";
import { jobsTable } from "./jobs-table";

export type BackendOutputs = {
  backendFunction: string;
  backendRegion: string;
  computeRoleArn: string;
  jobsTable: string;
};

function tagAll(parts: Record<string, Construct>, branch: string): void {
  for (const [component, part] of Object.entries(parts)) {
    Tags.of(part).add("pp:component", component);
    Tags.of(part).add("pp:branch", branch);
  }
}

function addOutputs(scope: Construct, named: Record<string, string>): void {
  for (const [name, value] of Object.entries(named)) {
    new CfnOutput(scope, name, { value });
  }
}

export class JobsBackend extends Construct {
  readonly outputs: BackendOutputs;
  readonly functions: lambda.Function[];

  constructor(scope: Construct, id: string) {
    super(scope, id);

    const table = jobsTable(this);
    const worker = workerFunction(this, table);
    const api = apiFunction(this, table, worker);
    const compute = computeRole(this, api.fn);

    configureBranch(this, compute);

    this.functions = [api.fn, worker.fn];

    const branch = process.env.AWS_BRANCH ?? "sandbox";

    const parts = {
      api: api.fn,
      worker: worker.fn,
      jobs: table,
      "compute-role": compute,
    };

    tagAll(parts, branch);

    this.outputs = {
      backendFunction: api.fn.functionName,
      backendRegion: Stack.of(this).region,
      computeRoleArn: compute.roleArn,
      jobsTable: table.tableName,
    };

    addOutputs(this, {
      ApiFunctionName: api.fn.functionName,
      WorkerFunctionName: worker.fn.functionName,
      ApiLogGroup: api.logGroup.logGroupName,
      WorkerLogGroup: worker.logGroup.logGroupName,
      JobsTableName: table.tableName,
      ComputeRoleArn: compute.roleArn,
    });
  }
}
