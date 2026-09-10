# AGENTS.md

This file provides guidance to AI coding assistants working in this repository.

## Project Overview

Personalised Planning is a GOV.UK service that helps users plan through complex life situations (e.g. learning to drive, bereavement) by generating personalised step-by-step plans using an AI agent backed by a UK government services knowledge graph.

## Architecture

The system has four main components:

1. **Agent** (`agent/app/`) — A Strands Agents Python app deployed via AWS Bedrock AgentCore. Receives a user situation, queries the service graph via MCP, and returns a structured plan (Pydantic `ResultPayload` model). Entry point: `main.py` → `planner_logic.py` → `planner_agent.py`.

2. **Backend** (`backend/`) — FastAPI service that acts as a gateway between the frontend and the agent. Supports two modes: `LOCAL_MODE=true` calls the agent over HTTP; `LOCAL_MODE=false` invokes the deployed AgentCore runtime via boto3.

3. **Frontend** (`frontend/`) — Next.js 16 app (React 19, pnpm). **Important**: This version of Next.js has breaking changes from training data — always read guides in `node_modules/next/dist/docs/` before writing frontend code.

4. **MCP Server** (`mcp-servers/service-graph/`) — TypeScript MCP server exposing the UK government services graph. Can run locally via stdio (`npx tsx src/graph-server.ts`) or deployed as a Lambda behind an AgentCore Gateway.

## Infrastructure & AgentCore

The `agentcore/` directory is a declarative model of the deployed infrastructure. The `agentcore/cdk/` subdirectory uses `@aws/agentcore-cdk` L3 constructs to deploy to AWS.

### Mental Model

The project uses a **flat resource model**. Agents, memories, credentials, gateways, evaluators, and policies are independent top-level arrays in `agentcore.json`. There is no binding between resources in the schema — each resource is provisioned independently. Agents discover memories and credentials at runtime via environment variables or SDK calls.

### Critical Invariants

1. **Schema-First Authority:** `agentcore.json` is the source of truth. Never edit generated CDK code in `cdk/` directly.
2. **Resource Identity:** The `name` field determines the CloudFormation Logical ID. **Renaming** destroys and recreates; modifying other fields updates in-place.
3. **Schema Validation:** Conform to types in `agentcore/.llm-context/*.ts`. Run `agentcore validate` to check.
4. **Resource Removal:** Use `agentcore remove`, then `agentcore deploy` to tear down.

### Schema Reference

| JSON Config | Schema File | Root Type |
| --- | --- | --- |
| `agentcore/agentcore.json` | `agentcore/.llm-context/agentcore.ts` | `AgentCoreProjectSpec` |
| `agentcore/agentcore.json` (gateways) | `agentcore/.llm-context/mcp.ts` | `AgentCoreMcpSpec` |
| `agentcore/aws-targets.json` | `agentcore/.llm-context/aws-targets.ts` | `AwsDeploymentTarget[]` |

When modifying JSON config files: read the corresponding `.llm-context/*.ts` file, check constraint comments (`@regex`, `@min`, `@max`), use exact enum string literals, use CloudFormation-safe names.

### AgentCore CLI

| Command | Description |
| --- | --- |
| `agentcore dev` | Run agent locally with hot-reload |
| `agentcore deploy` | Synthesize CDK and deploy to AWS |
| `agentcore status` | Show deployment status |
| `agentcore invoke` | Invoke agent (local or deployed) |
| `agentcore validate` | Validate configuration |
| `agentcore logs` / `traces` | View agent logs or traces |
| `agentcore add <resource>` | Add agent, memory, credential, gateway, evaluator, policy |
| `agentcore remove <resource>` | Remove a resource |
| `agentcore pause` / `resume` | Pause or resume a deployed agent |

## Development Commands

### Root project (Python)
```bash
uv sync --extra dev          # Install all dependencies
uv run ruff check --fix .    # Lint (auto-fix)
uv run ruff format .         # Format
uv run pytest tests/ -v      # Run tests
uv run pre-commit run --all-files  # Run all pre-commit hooks
```

### Backend
```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

### Agent (local)
```bash
cd agent/app
uv sync
uv run python main.py       # Starts BedrockAgentCoreApp on port 8080
```

### Frontend
```bash
cd frontend
pnpm install
pnpm dev                    # Next.js dev server on port 3000
pnpm lint                   # ESLint
```

### MCP Server
```bash
cd mcp-servers/service-graph
npm install
npm run mcp                 # Start local MCP server via stdio
```

### Docker (full stack)
```bash
docker compose up --build   # Agent (8080) + Backend (8000) together
```

Run under `aws-vault exec` to pass AWS credentials to the containers.

## Code Style

- Python: Ruff with 100 char line length, double quotes, LF line endings. Rules: E, W, F, I, B, C4, UP (E501 ignored). Target: 3.12+.
- TypeScript/Frontend: ESLint with next config.

## Key Environment Variables

See `.env.example` for the full list. Critical ones:
- `LOCAL_MODE` — `true`/`false` to toggle local vs deployed agent
- `ANTHROPIC_MODEL` — Bedrock model ID for the agent
- `MCP_MODE` — `local` (stdio) or `remote` (HTTP gateway)
- `GRAPH_SERVER_PATH` — path to MCP server source (local mode)
- `GRAPH_GATEWAY_URL` — deployed MCP gateway URL (remote mode)

## Workspace Structure

This is a uv workspace. The root `pyproject.toml` has workspace members:
- `scripts/evaluation/plan-generation` — evaluation scripts for generating synthetic profiles and comparing plans against ground truth

## CI

GitHub Actions (`.github/workflows/ci.yml`) runs on PRs to main:
- `uv run ruff check --fix .`
- `uv run detect-secrets scan --baseline .secrets.baseline`
- Tests are currently commented out in CI
