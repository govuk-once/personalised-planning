# Planner Backend

A single-endpoint FastAPI service that fronts the PersonalisedPlanning agent. It
can talk to the agent either as a locally-running process/container, or as a
deployed AgentCore runtime — controlled by one environment variable.

## Architecture

```
client → backend (/plan) → agent
```

- **Local mode** (`LOCAL_MODE=true`): the backend POSTs directly to
  the agent's `/invocations` HTTP endpoint (`AGENT_URL`). This is the same
  contract whether the agent is a bare local process or running in a
  container — `BedrockAgentCoreApp.run()` serves it either way.
- **AgentCore mode** (`LOCAL_MODE=false`): the backend calls the
  deployed AgentCore runtime via `boto3`'s `invoke_agent_runtime`. Agent
  invocations can take well over a minute (real runs have taken 60–80s), so
  the client is configured with a longer read timeout and retries disabled —
  see [Timeouts and retries](#timeouts-and-retries-agentcore-mode) below.


## Local development

### 1. First-time setup

```bash
cp .env.example .env
```

Fill in `.env` as needed (see `.env.example` in the root dir):

```
LOCAL_MODE=true
AGENT_URL=http://agent:8080/invocations
```

Make sure `backend/log_utils.py` exists (copied from wherever the canonical
version lives) — the app won't start without it. There is an outstanding task of moving these utils to a shared package.

### 2. Generate the lockfile (first time only, or after changing dependencies)

```bash
cd backend
uv lock
cd ..
```

Commit `backend/uv.lock` — this is what makes builds reproducible.

### 3. Build the containers

```bash
docker compose build
```

If you've changed a file and the build finishes suspiciously fast (e.g. `0.0s`)
without picking up the change, force a clean rebuild:

```bash
docker compose build --no-cache backend
```

### 4. Authenticate with AWS

Assume your team's development admin role:

```bash
gds-cli aws <admin-role> -e
```

### 5. Start everything

```bash
docker compose up
```

### 6. Check it's healthy

```bash
curl http://localhost:8000/health
```

Should return `{"status": "OK"}`. Worth also glancing at the `agent` logs in
your terminal to confirm it started cleanly before sending a real request.

### 7. Send a request to the backend (→ agent)

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

```bash
curl -X POST http://localhost:8000/plan \
  -H "Content-Type: application/json" \
  -H "X-Session-Id: $(uuidgen)" \
  -d '{"situation": "moving house"}'
```

### 8. Iterating on backend code

Two options while making changes:

- **Rebuild each time** (current default): after editing `backend/app/*.py`,

  ```bash
  docker compose build backend
  docker compose up
  ```

- **Hot-reload** (faster for active iteration): mount the app directory as a
  volume and pass `--reload` to uvicorn. Swap the `backend` service in
  `docker-compose.yml` for:

  ```yaml
  backend:
    build:
      context: ./backend
    ports:
      - "8000:8000"
    env_file:
      - .env
    volumes:
      - ./backend/app:/app/app
    command: ["uv", "run", "--frozen", "--no-dev", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
    depends_on:
      - agent
  ```

  With this, edits to `backend/app/*.py` take effect immediately without a
  rebuild or restart.


### 9. Shut down

```bash
docker compose down
```

## Testing against the deployed AgentCore runtime

Once an actual runtime is deployed and you have its ARN, set in `.env`:

```
LOCAL_MODE=false
AGENT_RUNTIME_ARN=<runtime arn>
AWS_DEFAULT_REGION=eu-west-2
```

Run just the backend (no local `agent` container needed):

```bash
docker compose up backend
```

Same `/plan` request as above works unchanged; the backend routes it to the
deployed runtime instead of the local HTTP call.
