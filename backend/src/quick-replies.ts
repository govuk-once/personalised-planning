import { labelsOf, withoutRepeats } from "./quick-reply-labels.ts";

const MIN_REPLIES = 2;
const MAX_REPLIES = 8;

export type DropReason =
  "off" | "complete" | "bad_label" | "amount" | "too_few" | "too_many";

export type Labels = {
  kept: string[];
  dropped: DropReason | null;
};

// "Under £6,000" can't be stored as a figure.
function namesAmount(label: string): boolean {
  return label.includes("£");
}

function verdict(kept: string[], dropped: DropReason | null): Labels {
  return {
    kept,
    dropped,
  };
}

// All or nothing: three nations without Northern Ireland would mislead.
export function judgeLabels(values: unknown[]): Labels {
  if (values.length === 0) {
    return verdict([], null);
  }

  const labels = labelsOf(values);

  if (labels === null) {
    return verdict([], "bad_label");
  }

  if (labels.some(namesAmount)) {
    return verdict([], "amount");
  }

  const kept = withoutRepeats(labels);

  if (kept.length < MIN_REPLIES) {
    return verdict([], "too_few");
  }

  if (kept.length > MAX_REPLIES) {
    return verdict([], "too_many");
  }

  return verdict(kept, null);
}
