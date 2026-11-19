import { type DropReason, judgeLabels } from "./quick-replies.ts";
import { listOrEmpty } from "./reply-fields.ts";
import type { Fields } from "./value-checks.ts";

export type AnswerFormat = "text" | "date";

export type AnswerHelpers = {
  quick_replies: string[];
  answer_format: AnswerFormat;
};

export type Offer = {
  shown: AnswerHelpers;
  offered: number;
  dropped: DropReason | null;
};

export type Conditions = {
  complete: boolean;
  enabled: boolean;
};

const NONE: AnswerHelpers = {
  quick_replies: [],
  answer_format: "text",
};

function formatOf(output: Fields): AnswerFormat {
  if (output.answer_format === "date") {
    return "date";
  }

  return "text";
}

function nothingShown(offered: number, dropped: DropReason | null): Offer {
  return {
    shown: NONE,
    offered,
    dropped,
  };
}

// Never throws: a turn must not fail over its options.
export function offerOf(output: Fields, conditions: Conditions): Offer {
  const values = listOrEmpty(output.quick_replies);
  const offered = values.length;
  const format = formatOf(output);
  const nothingOffered = offered === 0 && format === "text";

  if (nothingOffered) {
    return nothingShown(offered, null);
  }

  if (!conditions.enabled) {
    return nothingShown(offered, "off");
  }

  if (conditions.complete) {
    return nothingShown(offered, "complete");
  }

  const labels = judgeLabels(values);

  const shown = {
    quick_replies: labels.kept,
    answer_format: format,
  };

  return {
    shown,
    offered,
    dropped: labels.dropped,
  };
}

// Never the labels: they are the person's possible answers.
export function offerLogFields(offer: Offer): Fields {
  const fields: Fields = {
    quick_replies_offered: offer.offered,
  };

  if (offer.dropped) {
    fields.quick_replies_dropped = offer.dropped;
  }

  return fields;
}
