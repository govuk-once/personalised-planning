/** The kind of answer each fact takes, worked out from the rules that read it. */

import type { Answer, FieldRule } from './answer-types.js';
import { enumValuesOf } from './user-context.js';

function withoutRepeats<Value>(values: Value[]): Value[] {
  const distinct = new Set(values);

  return [...distinct];
}

function ascending(first: number, second: number): number {
  return first - second;
}

function thresholdsOf(rules: FieldRule[]): number[] {
  const thresholds: number[] = [];

  for (const rule of rules) {
    if (rule.type === 'comparison') {
      thresholds.push(rule.value);
    }
  }

  const distinct = withoutRepeats(thresholds);

  return distinct.sort(ascending);
}

// A rule lists only the values that pass it: examples, not the whole list.
function examplesOf(rules: FieldRule[]): string[] {
  const examples: string[] = [];

  for (const rule of rules) {
    if (rule.type === 'enum') {
      const passing = rule.oneOf.map(String);

      examples.push(...passing);
    }
  }

  return withoutRepeats(examples);
}

function listAnswer(field: string, rules: FieldRule[]): Answer {
  const allowed = enumValuesOf(field);

  if (allowed) {
    return {
      type: 'string',
      enum: [...allowed],
    };
  }

  return {
    type: 'string',
    examples: examplesOf(rules),
  };
}

export function answerFor(field: string, rules: FieldRule[]): Answer | undefined {
  const ruleTypes = rules.map(rule => rule.type);
  const types = new Set<string>(ruleTypes);

  if (types.has('deadline')) {
    return {
      type: 'string',
      format: 'date',
    };
  }

  if (types.has('comparison')) {
    return {
      type: 'number',
      thresholds: thresholdsOf(rules),
    };
  }

  if (types.has('enum')) {
    return listAnswer(field, rules);
  }

  if (types.has('boolean')) {
    return {
      type: 'boolean',
    };
  }

  // No rule reads the field: no answer type beats a guessed one.
  return undefined;
}
