import type { Attributes, Call, Input, Value } from "./dynamodb-call.ts";
import { PARTITION_KEY, SORT_KEY } from "./table.ts";

export type Summary = { wrote: string } | { read: string };

const KEYS = new Set([PARTITION_KEY, SORT_KEY]);

// Chatbot reply, just its length
const REPLY = "text";

const LONGEST_VALUE = 60;

function valueText(name: string, value: Value): string {
  const text = value.S ?? value.N;

  if (text !== undefined) {
    const hidden = name === REPLY || text.length > LONGEST_VALUE;

    return hidden ? `<${text.length} chars>` : text;
  }

  if (value.BOOL !== undefined) {
    return String(value.BOOL);
  }

  if (value.L) {
    return `<${value.L.length} items>`;
  }

  return "<map>";
}

function itemText(item: Attributes): string {
  const entries = Object.entries(item);
  const fields = entries.filter(([name]) => !KEYS.has(name));

  const pairs = fields.map(([name, value]) => {
    const text = valueText(name, value);

    return `${name}=${text}`;
  });

  return pairs.join(" ");
}

// "SET #status = :running" reads as "status=running".
function updateText(input: Input): string {
  const names = input.ExpressionAttributeNames ?? {};
  const values = input.ExpressionAttributeValues ?? {};
  const expression = input.UpdateExpression ?? "";
  const assignments = expression.replace("SET ", "").split(", ");

  const pairs = assignments.map(assignment => {
    const [left = "", right = ""] = assignment.split(" = ");
    const name = names[left] ?? left;
    const value = values[right];
    const text = value ? valueText(name, value) : right;

    return `${name}=${text}`;
  });

  return pairs.join(" ");
}

function readText(call: Call): string {
  if (call.operation === "Query") {
    const count = call.output.Count ?? 0;

    return `${count} items`;
  }

  if (!call.output.Item) {
    return "nothing";
  }

  return itemText(call.output.Item);
}

export function callSummary(call: Call): Summary {
  const { input } = call;

  if (input.Item) {
    const wrote = itemText(input.Item);

    return { wrote };
  }

  if (input.UpdateExpression) {
    const wrote = updateText(input);

    return { wrote };
  }

  const read = readText(call);

  return { read };
}
