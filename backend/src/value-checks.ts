export const SESSION_ID = /^[A-Za-z0-9._-]{33,128}$/;
export const JOB_ID = /^(chat|plan)-[0-9a-f]{32}$/;

export type Fields = Record<string, unknown>;

export function isRecord(value: unknown): value is Fields {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const isArray = Array.isArray(value);

  return !isArray;
}

export function isText(
  value: unknown,
  min: number,
  max: number
): value is string {
  if (typeof value !== "string") {
    return false;
  }

  return value.length >= min && value.length <= max;
}

export function isSessionId(value: unknown): value is string {
  if (typeof value !== "string") {
    return false;
  }

  return SESSION_ID.test(value);
}

export function isJobId(value: unknown): value is string {
  if (typeof value !== "string") {
    return false;
  }

  return JOB_ID.test(value);
}
