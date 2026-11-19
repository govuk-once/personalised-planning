import "server-only";

import type { InvokeCommand, InvokeCommandOutput, LambdaClient } from "@aws-sdk/client-lambda";

type HttpRequest = { headers?: Record<string, string> };

function addTraceHeader(command: InvokeCommand, header: string): void {
  command.middlewareStack.add(
    next => args => {
      const request = args.request as HttpRequest;

      if (request.headers) {
        request.headers["X-Amzn-Trace-Id"] = header;
      }

      return next(args);
    },
    {
      step: "build",
      name: "traceHeader",
    }
  );
}

export function sendWithTrace(
  client: LambdaClient,
  command: InvokeCommand,
  header: string
): Promise<InvokeCommandOutput> {
  addTraceHeader(command, header);

  return client.send(command);
}
