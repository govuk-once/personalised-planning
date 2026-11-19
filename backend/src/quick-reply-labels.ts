const MAX_LABEL_LENGTH = 40;

// Markup and invisible characters.
const UNSAFE = /[<>\p{Cc}\p{Cf}\p{Zl}\p{Zp}]/u;

function labelOf(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }

  const label = value.trim();
  const tooLong = label.length > MAX_LABEL_LENGTH;
  const unsafe = UNSAFE.test(label);

  if (label === "" || tooLong || unsafe) {
    return null;
  }

  return label;
}

export function labelsOf(values: unknown[]): string[] | null {
  const labels: string[] = [];

  for (const value of values) {
    const label = labelOf(value);

    if (label === null) {
      return null;
    }

    labels.push(label);
  }

  return labels;
}

export function withoutRepeats(labels: string[]): string[] {
  const seen = new Set<string>();
  const kept: string[] = [];

  for (const label of labels) {
    const key = label.toLowerCase();

    if (!seen.has(key)) {
      seen.add(key);
      kept.push(label);
    }
  }

  return kept;
}
