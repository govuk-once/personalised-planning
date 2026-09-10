# Planner Agent Pipeline

The first iteration of the planner agent pipeline comprises:
- Frontend client (`frontend/`)
- A single endpoint FastAPI backend service (`backend/`)
- PersonalisedPlanning agent (`PersonalisedPlanning/agent/app`).
```
client → backend (/plan) → agent
```

## Modes

In the initial set up frontend client and backend service are running locally.
The PersonalisedPlanning agent can run either as a locally-running process/container, or as a
deployed AgentCore runtime — controlled by one environment variable.

- **Local mode** (`LOCAL_MODE=true`): the backend POSTs directly to
  the agent's `/invocations` HTTP endpoint (`AGENT_URL`). This is the same
  contract whether the agent is a bare local process or running in a
  container — `BedrockAgentCoreApp.run()` serves it either way.
- **AgentCore mode** (`LOCAL_MODE=false`): the backend calls the
  deployed AgentCore runtime via `boto3`'s `invoke_agent_runtime`. Agent
  invocations can take well over a minute (real runs have taken 60–80s), so
  the client is configured with a longer read timeout and retries disabled —
  see [Timeouts and retries](#timeouts-and-retries-agentcore-mode) below.

### Two separate Dockerfiles/pyproject.toml for backend and agent

This backend has its own `Dockerfile` and `pyproject.toml`, entirely separate
from the agent's (`PersonalisedPlanning/agent/app/Dockerfile`):

- The agent's Dockerfile is managed by the AgentCore CLI and requires ARM64
  (Graviton) — constraints that don't apply to this backend.
- Dependency sets barely overlap (`claude-agent-sdk`/`bedrock-agentcore`/MCP
  tooling vs. `fastapi`/`uvicorn`/`httpx`).
- The two services deploy independently — the agent ships to AgentCore
  Runtime, the backend ships wherever the API is hosted (ECS, Lambda, etc.).

The root-level `Dockerfile`/`pyproject.toml` in this repo are unrelated repo
scaffolding (dev tooling config — `ruff`, `pytest`, `pre-commit`) and aren't
built or deployed by either service.


## Project layout

```
repo-root/
├── PersonalisedPlanning/
│   └── agent/
│       └── app/
│           └── Dockerfile     ← the real, deployed agent build
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── log_utils.py          ← shared logging module, copied in manually
│   └── app/
│       └── main.py
├── docker-compose.yml         ← local dev only, not part of any deploy path
└── .env.example
```

**Note:** `log_utils.py` is currently duplicated between the agent project and
this backend (copy-pasted, not shared as a package). Worth turning into a
proper internal package if it needs to change often — for now, any updates
have to be applied by hand in both places.


## Testing against the deployed AgentCore runtime

For more detail on setting up backend service see `backend/README.md`.

For quick set up, follow the following instructions:

1. Once an actual runtime is deployed and you have its ARN, set in `.env`:

```
LOCAL_MODE=false
AGENT_RUNTIME_ARN=<runtime arn>
AWS_DEFAULT_REGION=eu-west-2
```

2. Authenticate with AWS
3. Run just the backend (no local `agent` container needed):

```bash
docker compose up backend
```

4. In a different terminal send request to the endpoint:
```bash
curl -X POST http://localhost:8000/plan \
  -H "Content-Type: application/json" \
  -H "X-Session-Id: $(uuidgen)" \
  -d '{"situation": "moving house"}'
```

## Testing with a local agent

### 1. Set agent mode

```
LOCAL_MODE=true
AGENT_URL=http://agent:8080/invocations
```

### 2. Build the containers

```bash
docker compose build
```

If you've changed a file and the build finishes suspiciously fast (e.g. `0.0s`)
without picking up the change, force a clean rebuild:

```bash
docker compose build --no-cache
```

### 3. Authenticate with AWS

Assume your team's development admin role:

```bash
gds-cli aws <admin-role> -e
```

### 4. Start everything

```bash
docker compose up
```

### 5. Send a request to the backend (→ agent)
In a separate terminal authenticate with AWS and then send the request as follows:

```bash
curl -X POST http://localhost:8000/plan \
  -H "Content-Type: application/json" \
  -d '{"situation": "I want to apply for tax-free childcare", "user_context": {"age": 31, "location": "London"}}'
```

`user_context` is optional. `situation` is required.

**Optional: `X-Session-Id` header.** If omitted, the backend generates a
random session ID per request, so every call is treated as a brand-new,
unrelated conversation. Passing your own value matters in two ways:

- **Conversation continuity** — the same ID is passed through as
  `runtimeSessionId` to AgentCore, so repeated calls with the same ID hit the
  same session/microVM and the agent retains context between them. It also
  keeps the session "warm" under AgentCore's idle-session lifecycle, avoiding
  cold-start overhead on the next call.
- **Log correlation** — every `StructuredLogger` line (backend and agent)
  stamps `session_id`, so a known, chosen value is much easier to grep for in
  CloudWatch than a random UUID you'd have to look up first.
