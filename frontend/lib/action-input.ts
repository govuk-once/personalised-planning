import * as z from "zod";

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

const transcript = z.array(message).min(1).max(60);
const facts = z.record(z.string(), z.unknown());

export const chatInput = z.object({
  sessionId,
  messages: transcript,
  collectedFacts: facts.optional(),
  lifeEventIds: z.array(z.string()).optional(),
  outstanding: z.array(z.string()).optional(),
});

export const planInput = z.object({
  sessionId,
  situation: z.string().min(1).max(4_000),
  userContext: facts.optional(),
});

export type ChatInput = z.infer<typeof chatInput>;
export type PlanInput = z.infer<typeof planInput>;
