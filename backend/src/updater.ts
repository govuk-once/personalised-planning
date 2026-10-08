import {
  type DynamoDBClient,
  UpdateItemCommand,
} from "@aws-sdk/client-dynamodb";

import { hasName } from "./errors.ts";
import type { Attributes } from "./items.ts";
import type { Update } from "./updates.ts";

export type UpdateOutcome = {
  applied: boolean;
  item?: Attributes;
};

// A condition that fails is an expected outcome, not an error.
export function updater(client: DynamoDBClient, table: string) {
  return async function update(
    key: Attributes,
    change: Update,
    returnItem = false
  ): Promise<UpdateOutcome> {
    const returnValues = returnItem ? "ALL_NEW" : "NONE";

    const command = new UpdateItemCommand({
      TableName: table,
      Key: key,
      ...change,
      ReturnValues: returnValues,
    });

    try {
      const reply = await client.send(command);

      return {
        applied: true,
        item: reply.Attributes,
      };
    } catch (error) {
      if (hasName(error, "ConditionalCheckFailedException")) {
        return { applied: false };
      }

      throw error;
    }
  };
}
