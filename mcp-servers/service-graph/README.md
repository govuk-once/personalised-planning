# Deploying POC service graph

The service graph MCP server (graph-server.ts) was deployed to AWS as a serverless Lambda function exposed via AgentCore Gateway, replacing the local stdio process used during development.

## Approach
The existing stdio MCP server was wrapped using the @aws/run-mcp-servers-with-aws-lambda library, which bridges Lambda invocation events to the stdio process without requiring any changes to the server code itself. The Lambda handler spawns graph-server.mjs as a child process on each invocation, making the setup inherently stateless.
Both files were bundled separately using esbuild — lambda-handler.ts as CommonJS and graph-server.ts as ESM (required due to top-level await).


## Infrastructure

Lambda function: eu-west-2, nodejs20.x, 512MB
AgentCore Gateway: supplied to the agent at runtime via `GRAPH_GATEWAY_URL`
Gateway target: Lambda target with GATEWAY_IAM_ROLE credential provider and inline tool schemas

## IAM roles created

A Lambda execution role with the AWSLambdaBasicExecutionRole policy attached.
A gateway role that trusts bedrock-agentcore.amazonaws.com.

## Tools exposed

govuk-graph-lambda-target___list_life_events
govuk-graph-lambda-target___plan_journey
govuk-graph-lambda-target___get_service
govuk-graph-lambda-target___check_eligibility
govuk-graph-lambda-target___get_required_information

**Note:** `get_required_information` was added to `graph-server.ts` after the initial Lambda deploy. The Lambda must be redeployed (steps below) before the conversation agent can use it in AgentCore mode.

## Redeployment
1. Build and bundle
```bash
cd mcp-servers/service-graph
npm run build:lambda
```

2. Zip the code
```bash
npm run package
```

3. Push new code to Lambda (make sure you are authenticated with AWS)
```bash
aws lambda update-function-code \
  --function-name <lambda-function-name> \
  --zip-file fileb://function.zip \
  --region eu-west-2
```
