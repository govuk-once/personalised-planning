import { BedrockAgentCoreClient } from "@aws-sdk/client-bedrock-agentcore";
import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { LambdaClient } from "@aws-sdk/client-lambda";

// Endpoints come from AWS_ENDPOINT_URL_DYNAMODB and _LAMBDA, read by the SDK itself.

// socketTimeout covers a response that stalls after its headers.
export function dynamoDb(region: string, maxAttempts = 2): DynamoDBClient {
  return new DynamoDBClient({
    region,
    maxAttempts,
    requestHandler: {
      connectionTimeout: 1_000,
      requestTimeout: 3_000,
      socketTimeout: 3_000,
      throwOnRequestTimeout: true,
    },
  });
}

// Five tries ride out the brief throttling a burst of result parts can cause.
export function patientDynamoDb(region: string): DynamoDBClient {
  return dynamoDb(region, 5);
}

export function lambda(region: string): LambdaClient {
  return new LambdaClient({
    region,
    maxAttempts: 2,
    requestHandler: {
      connectionTimeout: 2_000,
      requestTimeout: 4_000,
      socketTimeout: 4_000,
      throwOnRequestTimeout: true,
    },
  });
}

// One attempt only as an agent call is slow
export function agentCore(region: string): BedrockAgentCoreClient {
  return new BedrockAgentCoreClient({
    region,
    maxAttempts: 1,
    requestHandler: { connectionTimeout: 10_000 },
  });
}
