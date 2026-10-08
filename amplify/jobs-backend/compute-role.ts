import { Stack } from "aws-cdk-lib";
import * as iam from "aws-cdk-lib/aws-iam";
import * as lambda from "aws-cdk-lib/aws-lambda";
import { Construct } from "constructs";

const DESCRIPTION =
  "Amplify SSR compute (Next.js server): may invoke the backend Api Lambda, nothing else";

export function computeRole(scope: Construct, api: lambda.IFunction): iam.Role {
  const account = Stack.of(scope).account;

  const principal = new iam.ServicePrincipal("amplify.amazonaws.com", {
    conditions: {
      StringEquals: { "aws:SourceAccount": account },
    },
  });

  const role = new iam.Role(scope, "ComputeRole", {
    assumedBy: principal,
    description: DESCRIPTION,
  });

  api.grantInvoke(role);

  return role;
}
