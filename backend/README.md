# Backend

Two Node.js 24 Lambdas between the Next.js server and the two agents.

```
Next.js Server Action → Api Lambda → DynamoDB jobs table
                           └→ Worker Lambda (async) → agent → saves the reply to the job
```

- **Api** (`src/api-handler.ts`): `start_chat` and `start_plan` save a pending job and start the Worker. `get_job` returns the job. The page polls it.
- **Worker** (`src/worker-handler.ts`): calls the agent and saves its reply.
- Infrastructure: `amplify/jobs-backend/`. Amplify handles deploy.
- `MAX_WORKERS` in `amplify/jobs-backend/functions.ts`.

## Check it

```bash
cd backend
npm ci
npm run typecheck
npm run lint
npm run format
```

## Run it locally

Needs Docker, AWS SAM CLI and DynamoDB Local on port 8001 (`docker compose up dynamodb`).

```bash
# from the repository root
npm install
LOCAL_MODE=true npm run backend:local
AWS_ACCESS_KEY_ID=local AWS_SECRET_ACCESS_KEY=local aws dynamodb create-table \
  --endpoint-url http://localhost:8001 --region eu-west-2 \
  --cli-input-json "$(jq -c .table.definition .local/backend.json)"
sam local start-lambda --template .local/cdk.out/PpLocal.template.json --port 8002 --region eu-west-2 &
sam local start-lambda --template .local/cdk.out/PpLocal.template.json --port 8000 --region eu-west-2 --warm-containers EAGER
```

- `LOCAL_MODE=true` uses agents on ports 8080 and 8081. Leave it out to use the deployed agents: set `AGENT_RUNTIME_ARN` and `CHAT_AGENT_RUNTIME_ARN`, and start SAM with AWS credentials.
- Start the frontend with `BACKEND_FUNCTION_NAME=$(jq -r .apiFunction ../.local/backend.json)` and `BACKEND_LAMBDA_ENDPOINT=http://127.0.0.1:8000`.
- After changing `backend/src`, run `npm run backend:local` again.
