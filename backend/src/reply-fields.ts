import { type Fields, isRecord } from "./value-checks.ts";

export function recordOrEmpty(value: unknown): Fields {
  if (isRecord(value)) {
    return value;
  }

  return {};
}

export function recordOrNull(value: unknown): Fields | null {
  if (isRecord(value)) {
    return value;
  }

  return null;
}

export function listOrEmpty(value: unknown): unknown[] {
  if (Array.isArray(value)) {
    return value;
  }

  return [];
}

export function textOrNull(value: unknown): string | null {
  if (typeof value === "string") {
    return value;
  }

  return null;
}

export function outputOf(reply: unknown): Fields {
  if (!isRecord(reply)) {
    return {};
  }

  if ("output" in reply) {
    return recordOrEmpty(reply.output);
  }

  return reply;
}
