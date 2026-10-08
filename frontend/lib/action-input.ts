import * as z from "zod";

import { fitsFacts, fitsTranscript, TOO_LONG_ISSUE } from "@/lib/input-limits";

// validate every input.

const ID_CHARACTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_";

const sessionId = z
  .string()
  .min(33, "AgentCore rejects session ids shorter than 33 characters")
  .max(128)
  .refine(
    value => [...value].every(character => ID_CHARACTERS.includes(character)),
    "A session id becomes an HTTP header, so it may only contain letters, digits, . - and _"
  );

// No min length: an agent may emit an empty message, and the transcript must stay replayable.
const message = z.object({
  role: z.enum(["user", "assistant"]),
  content: z.string().max(20_000),
});

const transcript = z
  .array(message)
  .min(1)
  .max(60)
  .refine(fitsTranscript, TOO_LONG_ISSUE);

const facts = z.record(z.string(), z.unknown()).refine(fitsFacts, TOO_LONG_ISSUE);

function ownJobId(kind: "chat" | "plan") {
  const pattern = new RegExp(`^${kind}-[0-9a-f]{32}$`);

  return z.string().regex(pattern);
}

export const chatInput = z.object({
  sessionId,
  jobId: ownJobId("chat").optional(),
  messages: transcript,
  collectedFacts: facts.optional(),
  lifeEventIds: z.array(z.string()).optional(),
  outstanding: z.array(z.string()).optional(),
});

export const jobLookup = z.object({
  sessionId,
  jobId: z.string().regex(/^(chat|plan)-[0-9a-f]{32}$/),
});

export const planInput = z.object({
  sessionId,
  jobId: ownJobId("plan").optional(),
  situation: z.string().min(1).max(4_000),
  userContext: facts.optional(),
});

export type ChatInput = z.infer<typeof chatInput>;
export type PlanInput = z.infer<typeof planInput>;
export type JobLookup = z.infer<typeof jobLookup>;
