const MAX_TRANSCRIPT_CHARS = 100_000;
const MAX_FACTS_CHARS = 20_000;

export const TOO_LONG_ISSUE = "too_long";

type Message = {
  content: string;
};

function totalLength(messages: Message[]): number {
  return messages.reduce((sum, { content }) => sum + content.length, 0);
}

export function fitsTranscript(messages: Message[]): boolean {
  return totalLength(messages) <= MAX_TRANSCRIPT_CHARS;
}

export function fitsFacts(value: Record<string, unknown>): boolean {
  const json = JSON.stringify(value);

  return json.length <= MAX_FACTS_CHARS;
}

type Issue = {
  code: string;
  message: string;
};

const TOO_LONG = "This conversation is too long to send. Please start again.";
const NOT_SENT = "That conversation could not be sent.";

function isTooLong(issues: Issue[]): boolean {
  return issues.some(issue => {
    const overLimit = issue.code === "too_big";

    return overLimit || issue.message === TOO_LONG_ISSUE;
  });
}

export function chatRefusal(issues: Issue[]): string {
  if (isTooLong(issues)) {
    return TOO_LONG;
  }

  return NOT_SENT;
}
