# AGENTS.md

This file provides guidance to AI coding assistants working in this repository.

## Project Overview

Personalised Planning is a GOV.UK service that helps users plan through complex life situations (e.g. learning to drive, bereavement) by generating personalised step-by-step plans using an AI agent backed by a UK government services knowledge graph.

## Architecture

The system has four main components:

1. **Agents** (`agent/`) — Two Python agent runtimes deployed via AWS Bedrock AgentCore, sharing common code in `agent/shared/`:
   - **Planner** (`agent/app/`) — receives a user situation, queries the service graph via MCP, and returns a structured plan (Pydantic `ResultPayload` model). Entry point: `main.py` → `planner_logic.py` → `planner_agent.py`.
   - **Conversation** (`agent/chat/`) — an information-gathering agent that takes the conversation so far and returns the next question plus collected facts, looping until it has enough to plan (a `ConversationTurn` with a `complete` flag). Entry point: `main.py` → `chat_logic.py` → `chat_agent.py`.

2. **Backend** (`backend/`) — FastAPI service that acts as a gateway between the frontend and the two agents. Exposes `POST /chat` (→ conversation agent) and `POST /plan` (→ planner agent). Supports two modes: `LOCAL_MODE=true` calls each agent over HTTP; `LOCAL_MODE=false` invokes the deployed AgentCore runtimes via boto3.

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

Dependencies and the lockfile now live at `agent/` (shared by both `app/` and `chat/`).
Sync once from there, then run whichever agent from its subdirectory — `PYTHONPATH=..`
makes `shared/` importable and running from the subdir lets `./system_prompt.md` resolve
(this mirrors the Dockerfiles' `WORKDIR` + `PYTHONPATH=/app`).

```bash
cd agent
uv sync                                     # deps + lockfile at agent/

# Planner (port 8080):
(cd app && PYTHONPATH=.. uv run python main.py)

# Conversation agent (run separately):
(cd chat && PYTHONPATH=.. uv run python main.py)
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

The backend and agents are configured via environment variables (set in `.env`). Critical ones:
- `LOCAL_MODE` — `true`/`false` to toggle local HTTP agents vs deployed AgentCore runtimes
- `AGENT_URL` / `CHAT_AGENT_URL` — planner / conversation agent HTTP endpoints (local mode)
- `AGENT_RUNTIME_ARN` / `CHAT_AGENT_RUNTIME_ARN` — deployed runtime ARNs (AgentCore mode)
- `ANTHROPIC_MODEL` — Bedrock model ID for the agents
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
