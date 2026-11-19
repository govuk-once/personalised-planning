/** The kind of answer each fact takes, in the types MCP elicitation uses. */

import type { Rule } from './rules.js';

type YesNoAnswer = {
  type: 'boolean';
};

type NumberAnswer = {
  type: 'number';
  thresholds: number[];
};

type ListAnswer = {
  type: 'string';
  enum: string[];
};

type ExamplesAnswer = {
  type: 'string';
  examples: string[];
};

type DateAnswer = {
  type: 'string';
  format: 'date';
};

export type Answer = YesNoAnswer | NumberAnswer | ListAnswer | ExamplesAnswer | DateAnswer;

type FieldRuleType = 'comparison' | 'boolean' | 'enum' | 'deadline';

export type FieldRule = Extract<Rule, { type: FieldRuleType }>;
