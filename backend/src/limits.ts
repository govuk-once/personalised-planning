import type { Message } from "./requests.ts";
import { isRecord, isText } from "./value-checks.ts";

export const LIMITS = {
  messages: 60,
  messageChars: 20_000,
  transcriptChars: 100_000,
  contextChars: 20_000,
  situationChars: 4_000,
};

// Lambda refuses an asynchronous invocation over 1 MB
export const MAX_WORKER_EVENT_BYTES = 1_000_000;

function isMessage(value: unknown): value is Message {
  if (!isRecord(value)) {
    return false;
  }

  const knownRole = value.role === "user" || value.role === "assistant";

  if (!knownRole) {
    return false;
  }

  return isText(value.content, 0, LIMITS.messageChars);
}

function totalChars(messages: Message[]): number {
  return messages.reduce((sum, message) => sum + message.content.length, 0);
}

export function isTranscript(value: unknown): value is Message[] {
  if (!Array.isArray(value)) {
    return false;
  }

  if (value.length < 1 || value.length > LIMITS.messages) {
    return false;
  }

  if (!value.every(isMessage)) {
    return false;
  }

  const chars = totalChars(value);

  return chars <= LIMITS.transcriptChars;
}

export function isContext(value: unknown): boolean {
  if (value === undefined || value === null) {
    return true;
  }

  if (!isRecord(value)) {
    return false;
  }

  const json = JSON.stringify(value);

  return json.length <= LIMITS.contextChars;
}

export function byteLength(value: unknown): number {
  const json = JSON.stringify(value);

  return Buffer.byteLength(json, "utf8");
}
