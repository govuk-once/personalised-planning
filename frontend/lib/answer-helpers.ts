import type { StoredConversation } from "@/lib/session";
import type { ChatTurn } from "@/lib/types";

export type AnswerFormat = "text" | "date";

export type AnswerHelpers = {
  quickReplies: string[];
  answerFormat: AnswerFormat;
};

const NONE: AnswerHelpers = {
  quickReplies: [],
  answerFormat: "text",
};

function isLabel(option: unknown): option is string {
  if (typeof option !== "string") {
    return false;
  }

  return option.trim() !== "";
}

function labelsFrom(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }

  const options: unknown[] = value;

  if (!options.every(isLabel)) {
    return [];
  }

  return options;
}

function formatFrom(value: unknown): AnswerFormat {
  if (value === "date") {
    return "date";
  }

  return "text";
}

// Unchecked input: a job result, or storage written by another version of the page.
function helpersFrom(quickReplies: unknown, answerFormat: unknown): AnswerHelpers {
  const labels = labelsFrom(quickReplies);
  const format = formatFrom(answerFormat);

  return {
    quickReplies: labels,
    answerFormat: format,
  };
}

export function helpersOf(turn: ChatTurn): AnswerHelpers {
  return helpersFrom(turn.quick_replies, turn.answer_format);
}

export function helpersShown(conversation: StoredConversation, pending: boolean): AnswerHelpers {
  const last = conversation.messages.at(-1);
  const asking = last?.role === "assistant";

  if (pending || conversation.complete || !asking) {
    return NONE;
  }

  return helpersFrom(conversation.quickReplies, conversation.answerFormat);
}

export function offersHelp(helpers: AnswerHelpers): boolean {
  const hasButtons = helpers.quickReplies.length > 0;
  const hasDatePicker = helpers.answerFormat === "date";

  return hasButtons || hasDatePicker;
}
