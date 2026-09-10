import { anthropic } from "@ai-sdk/anthropic";
import { convertToModelMessages, streamText, tool } from "ai";
import * as z from 'zod';

export const maxDuration = 30;

export async function POST(req: Request) {
  const { messages, system } = await req.json();

  const result = streamText({
    model: anthropic("claude-sonnet-4-6"),
    system,
    messages: await convertToModelMessages(messages),
    tools: {
      renderButtonLink: tool({
        description: "Render a button link to the '/plan' route",
        inputSchema: z.object({}),
        execute: async () => {
          return "Button Link rendered"
        },
      }),
    }
  });

  return result.toUIMessageStreamResponse();
}
