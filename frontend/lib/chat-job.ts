import type { Answer } from "@/lib/answer-tracking";
import { freshJob } from "@/lib/job-id";
import type { StoredChatJob } from "@/lib/session";

export function chatJobFor(text: string, answer: Answer): StoredChatJob {
  const fresh = freshJob("chat");

  return {
    ...fresh,
    text,
    answeredBy: answer.by,
  };
}
