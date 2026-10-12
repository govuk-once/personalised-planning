import "server-only";

import { InvokeCommand, LambdaClient } from "@aws-sdk/client-lambda";

const LOCAL_CREDENTIALS = {
  accessKeyId: "local",
  secretAccessKey: "local", // pragma: allowlist secret
};

export class BackendUnavailable extends Error {}

const NO_COMPUTE_ROLE =
  "is the branch's compute role attached? Amplify: App settings, IAM roles, Compute role";

export function describeFailure(error: unknown): string {
  const text = String(error);
  const noCredentials = error instanceof Error && error.name === "CredentialsProviderError";

  if (noCredentials) {
    return `${text} (${NO_COMPUTE_ROLE})`;
  }

  return text;
}

let client: LambdaClient | null = null;

function region(): string {
  return process.env.BACKEND_REGION ?? process.env.AWS_REGION ?? "eu-west-2";
}

function localOptions(endpoint: string | undefined) {
  if (!endpoint) {
    return {};
  }

  return {
    endpoint,
    credentials: LOCAL_CREDENTIALS,
  };
}

function lambda(endpoint: string | undefined): LambdaClient {
  if (client) {
    return client;
  }

  const backendRegion = region();
  const local = localOptions(endpoint);

  client = new LambdaClient({
    region: backendRegion,
    maxAttempts: 1,
    requestHandler: {
      connectionTimeout: 3_000,
      requestTimeout: 16_000,
      socketTimeout: 16_000,
      throwOnRequestTimeout: true,
    },
    ...local,
  });

  return client;
}

export async function callBackend<T>(event: Record<string, unknown>): Promise<T> {
  const functionName = process.env.BACKEND_FUNCTION_NAME;

  if (!functionName) {
    throw new BackendUnavailable("BACKEND_FUNCTION_NAME is not set");
  }

  const endpoint = process.env.BACKEND_LAMBDA_ENDPOINT;
  const backend = lambda(endpoint);

  const json = JSON.stringify(event);
  const payload = new TextEncoder().encode(json);

  const command = new InvokeCommand({
    FunctionName: functionName,
    InvocationType: "RequestResponse",
    Payload: payload,
  });

  const response = await backend.send(command);
  const body = new TextDecoder().decode(response.Payload);

  if (response.FunctionError) {
    const excerpt = body.slice(0, 300);

    throw new BackendUnavailable(`${response.FunctionError}: ${excerpt}`);
  }

  return JSON.parse(body) as T;
}
