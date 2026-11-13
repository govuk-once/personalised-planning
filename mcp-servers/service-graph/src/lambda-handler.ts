import { Handler, Context } from "aws-lambda";
import {
  BedrockAgentCoreGatewayTargetHandler,
  StdioServerAdapterRequestHandler,
} from "@aws/run-mcp-servers-with-aws-lambda";

import path from "path";

import { log } from "./tool-log.js";

type ToolResult = Record<string, unknown>;

type GatewayContext = {
  custom?: { bedrockAgentCoreToolName?: string };
};

const serverParams = {
  command: "node",
  args: [path.join(process.env.LAMBDA_TASK_ROOT ?? ".", "dist/graph-server.mjs")],
};

const requestHandler = new BedrockAgentCoreGatewayTargetHandler(
  new StdioServerAdapterRequestHandler(serverParams)
);

// The gateway names the tool it is calling in the client context.
function toolName(context: Context): string | undefined {
  const gateway = context.clientContext as unknown as GatewayContext | undefined;

  return gateway?.custom?.bedrockAgentCoreToolName;
}

export const handler: Handler = async (
  event: Record<string, unknown>,
  context: Context
): Promise<ToolResult> => {
  const tool = toolName(context);
  const startMs = Date.now();

  try {
    const result = (await requestHandler.handle(event, context)) as ToolResult;
    const answer = JSON.stringify(result);

    log("INFO", "Tool called", {
      tool,
      arguments: event,
      answer_chars: answer.length,
      ms: Date.now() - startMs,
    });

    return result;
  } catch (error) {
    log("ERROR", "Tool failed", {
      tool,
      arguments: event,
      error: String(error),
    });

    throw error;
  }
};
