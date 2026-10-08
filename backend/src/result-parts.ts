import { type DynamoDBClient, QueryCommand } from "@aws-sdk/client-dynamodb";

import {
  type Attributes,
  keyOf,
  partKey,
  partPrefix,
  toAttribute,
} from "./items.ts";
import type { ClaimedJob } from "./jobs.ts";
import { updater } from "./updater.ts";
import { createOnce } from "./updates.ts";

const PARTS_OF_RUN = "session_id = :session AND begins_with(item_key, :prefix)";

function textsOf(items: Attributes[]): string[] {
  return items.map(item => item.text?.S ?? "");
}

export function resultParts(client: DynamoDBClient, table: string) {
  const update = updater(client, table);

  function queryPage(
    sessionId: string,
    jobId: string,
    runId: string,
    startKey?: Attributes
  ) {
    const prefix = partPrefix(jobId, runId);
    const sessionValue = toAttribute(sessionId);
    const prefixValue = toAttribute(prefix);

    const command = new QueryCommand({
      TableName: table,
      KeyConditionExpression: PARTS_OF_RUN,
      ExpressionAttributeValues: {
        ":session": sessionValue,
        ":prefix": prefixValue,
      },
      ConsistentRead: true,
      ExclusiveStartKey: startKey,
    });

    return client.send(command);
  }

  // Create-only: a part that exists already is this run's own, from a retry.
  async function writePart(job: ClaimedJob, index: number, text: string) {
    const itemKey = partKey(job.job_id, job.run_id, index);
    const key = keyOf(job.session_id, itemKey);

    const part = {
      job_id: job.job_id,
      part: index,
      text,
      expires_at: job.expires_at,
    };

    const change = createOnce(part);

    await update(key, change);
  }

  return {
    async writeParts(job: ClaimedJob, texts: string[]): Promise<void> {
      for (const [index, text] of texts.entries()) {
        await writePart(job, index, text);
      }
    },

    // The zero-padded index keeps parts in order across 1 MB query pages.
    async readParts(
      sessionId: string,
      jobId: string,
      runId: string
    ): Promise<string[]> {
      const texts: string[] = [];
      let startKey: Attributes | undefined;

      do {
        const page = await queryPage(sessionId, jobId, runId, startKey);
        const items = page.Items ?? [];
        const pageTexts = textsOf(items);

        texts.push(...pageTexts);
        startKey = page.LastEvaluatedKey;
      } while (startKey);

      return texts;
    },
  };
}
