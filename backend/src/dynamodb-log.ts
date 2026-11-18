import type { DynamoDBClient } from "@aws-sdk/client-dynamodb";

import type { Call, Failure, Input, Output } from "./dynamodb-call.ts";
import { reportCall } from "./dynamodb-report.ts";

// Logging for X-Ray traces
export function logDynamoDb(client: DynamoDBClient): DynamoDBClient {
  client.middlewareStack.add(
    (next, context) => async args => {
      const command = context.commandName ?? "";
      const startMs = Date.now();

      const call: Call = {
        operation: command.replace("Command", ""),
        input: args.input as Input,
        output: {},
        failure: null,
        startMs,
      };

      try {
        const result = await next(args);
        const output = result.output as Output;

        reportCall({ ...call, output });

        return result;
      } catch (error) {
        const failure = error as Failure;

        reportCall({ ...call, failure });

        throw error;
      }
    },
    {
      step: "initialize",
      name: "logDynamoDb",
    }
  );

  return client;
}
