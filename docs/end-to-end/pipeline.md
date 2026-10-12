# Pipeline

Needs Docker, gds-cli, `make`, Node.js 24+, pnpm, AWS CLI, `jq` and the AWS SAM CLI. First run:

```bash
export AWS_PROFILE=<aws role name>
```

## Run locally

```bash
cp .env.example .env
make local-setup
make local
```

Next time, just `make local`.

## Check each part

```bash
# Next.js
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:3000
# Planner agent
curl -s -w '\n' http://localhost:8080/ping
# Conversation agent
curl -s -w '\n' http://localhost:8081/ping
# Conversation agent, one message
curl -s -w '\n' http://localhost:8081/invocations -d '{"messages":[{"role":"user","content":"I have just had a baby"}]}'
# Api Lambda: start a chat job
API=http://localhost:8000/2015-03-31/functions/$(jq -r .apiFunction .local/backend.json)/invocations
curl -s -w '\n' "$API" -d '{"action":"start_chat","session_id":"curl-0000000000000000000000000000001","job_id":"chat-00000000000000000000000000000001","messages":[{"role":"user","content":"I have just had a baby"}]}'
# Api Lambda: read the job
curl -s -w '\n' "$API" -d '{"action":"get_job","session_id":"curl-0000000000000000000000000000001","job_id":"chat-00000000000000000000000000000001"}'
```

## Inspect the local DynamoDB

```bash
unset AWS_PROFILE
export AWS_ACCESS_KEY_ID=local AWS_SECRET_ACCESS_KEY=local AWS_REGION=eu-west-2 AWS_ENDPOINT_URL_DYNAMODB=http://localhost:8001
TABLE=$(aws dynamodb list-tables --query 'TableNames[0]' --output text)
aws dynamodb scan --table-name "$TABLE" --query 'Items[].[session_id.S, item_key.S, kind.S, status.S]' --output table
aws dynamodb scan --table-name "$TABLE"
```
