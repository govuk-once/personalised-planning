export type Value = {
  S?: string;
  N?: string;
  BOOL?: boolean;
  L?: unknown[];
};

export type Attributes = Record<string, Value>;

export type Input = {
  TableName?: string;
  Key?: Attributes;
  Item?: Attributes;
  UpdateExpression?: string;
  ExpressionAttributeNames?: Record<string, string>;
  ExpressionAttributeValues?: Attributes;
};

export type Output = {
  Item?: Attributes;
  Count?: number;
};

export type Failure = {
  name?: string;
  $metadata?: { httpStatusCode?: number };
};

export type Call = {
  operation: string;
  input: Input;
  output: Output;
  failure: Failure | null;
  startMs: number;
};
