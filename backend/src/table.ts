// The CDK stack and the DynamoDB Local tests build the jobs table from these.
export const PARTITION_KEY = "session_id";
export const SORT_KEY = "item_key";
export const TTL_ATTRIBUTE = "expires_at";
