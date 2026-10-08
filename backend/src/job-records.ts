import {
  type DynamoDBClient,
  GetItemCommand,
  PutItemCommand,
} from "@aws-sdk/client-dynamodb";

import { jobChanges } from "./job-changes.ts";
import { jobFromItem, jobItem, keyOfJob } from "./items.ts";
import type { Job } from "./jobs.ts";

export function jobRecords(client: DynamoDBClient, table: string) {
  const changes = jobChanges(client, table);

  return {
    async putJob(job: Job): Promise<void> {
      const item = jobItem(job);

      const command = new PutItemCommand({
        TableName: table,
        Item: item,
        ConditionExpression: "attribute_not_exists(item_key)",
      });

      await client.send(command);
    },

    async getJob(sessionId: string, jobId: string): Promise<Job | null> {
      const key = keyOfJob(sessionId, jobId);

      const command = new GetItemCommand({
        TableName: table,
        Key: key,
        ConsistentRead: true,
      });

      const reply = await client.send(command);

      if (!reply.Item) {
        return null;
      }

      return jobFromItem(reply.Item);
    },

    ...changes,
  };
}
