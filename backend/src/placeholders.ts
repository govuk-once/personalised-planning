import { type Attributes, type Plain, toAttribute } from "./items.ts";

const NAMES: Record<string, string> = {
  "#status": "status",
  "#run": "run_id",
  "#created": "created_at",
  "#started": "started_at",
  "#finished": "finished_at",
  "#parts": "result_parts",
  "#error": "error",
};

const STATUSES: Record<string, Plain> = {
  ":pending": "pending",
  ":running": "running",
  ":done": "done",
  ":failed": "failed",
};

export function toValues(plain: Record<string, Plain>): Attributes {
  const values: Attributes = {};

  for (const [name, value] of Object.entries(plain)) {
    values[name] = toAttribute(value);
  }

  return values;
}

function placeholdersIn(expressions: string[], pattern: RegExp): Set<string> {
  const found = expressions.flatMap(expression => {
    return expression.match(pattern) ?? [];
  });

  return new Set(found);
}

// DynamoDB refuses any name or value that no expression uses.
export function namesIn(expressions: string[]): Record<string, string> {
  const used = placeholdersIn(expressions, /#\w+/g);
  const names = [...used].map(name => [name, NAMES[name]]);

  return Object.fromEntries(names);
}

export function valuesIn(
  expressions: string[],
  plain: Record<string, Plain>
): Attributes {
  const used = placeholdersIn(expressions, /:\w+/g);

  const candidates = {
    ...STATUSES,
    ...plain,
  };

  const entries = Object.entries(candidates);
  const usedEntries = entries.filter(([name]) => used.has(name));
  const usedPlain = Object.fromEntries(usedEntries);

  return toValues(usedPlain);
}
