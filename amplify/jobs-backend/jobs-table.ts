import { RemovalPolicy } from "aws-cdk-lib";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import { Construct } from "constructs";

import {
  PARTITION_KEY,
  SORT_KEY,
  TTL_ATTRIBUTE,
} from "../../backend/src/table";

export function jobsTable(scope: Construct): dynamodb.Table {
  return new dynamodb.Table(scope, "Jobs", {
    partitionKey: {
      name: PARTITION_KEY,
      type: dynamodb.AttributeType.STRING,
    },
    sortKey: {
      name: SORT_KEY,
      type: dynamodb.AttributeType.STRING,
    },
    billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
    timeToLiveAttribute: TTL_ATTRIBUTE,
    encryption: dynamodb.TableEncryption.DEFAULT,
    pointInTimeRecoverySpecification: { pointInTimeRecoveryEnabled: false },
    deletionProtection: false,
    removalPolicy: RemovalPolicy.DESTROY,
  });
}
