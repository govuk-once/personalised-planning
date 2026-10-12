// JSON.stringify never emits a lone surrogate, so a part of 100,000 UTF-16 code
// units is at most 300,000 bytes: well under DynamoDB's 400 KB item limit.
export const PART_LENGTH = 100_000;
export const MAX_RESULT_LENGTH = 1_000_000;

function isHighSurrogate(code: number): boolean {
  return code >= 0xd800 && code <= 0xdbff;
}

function endOfPart(text: string, start: number, partLength: number): number {
  const limit = start + partLength;
  const end = Math.min(limit, text.length);

  if (end >= text.length) {
    return end;
  }

  const lastCode = text.charCodeAt(end - 1);

  if (isHighSurrogate(lastCode)) {
    return end - 1;
  }

  return end;
}

export function splitIntoParts(
  text: string,
  partLength = PART_LENGTH
): string[] {
  const parts: string[] = [];
  let start = 0;

  while (start < text.length) {
    const end = endOfPart(text, start, partLength);
    const part = text.slice(start, end);

    parts.push(part);
    start = end;
  }

  return parts;
}

export function joinParts(parts: string[]): string {
  return parts.join("");
}

export function utf8Bytes(text: string): number {
  return Buffer.byteLength(text, "utf8");
}
