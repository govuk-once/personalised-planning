export type Traceparent = {
  traceId: string;
  parentId: string;
};

const HEX_DIGITS = "0123456789abcdef";

function isHex(text: string, length: number): boolean {
  const digits = [...text];
  const allHex = digits.every(digit => HEX_DIGITS.includes(digit));

  return digits.length === length && allHex;
}

// The browser sends "00-<trace id>-<parent id>-<flags>", so it is checked.
export function parseTraceparent(header: string | null | undefined): Traceparent | null {
  const parts = header?.split("-") ?? [];
  const [version, traceId = "", parentId = "", flags = ""] = parts;

  const validIds = isHex(traceId, 32) && isHex(parentId, 16);
  const validEnds = version === "00" && isHex(flags, 2);

  if (!validIds || !validEnds) {
    return null;
  }

  return {
    traceId,
    parentId,
  };
}
