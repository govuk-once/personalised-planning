# Planner Backend

A FastAPI service that fronts two AgentCore agent runtimes. It can talk to each agent either as a locally-running process/container, or as a deployed AgentCore runtime — controlled by one environment variable.

## Architecture

```
client → backend (/chat)  → conversation agent  (gathers information)
client → backend (/plan)  → planner agent        (produces the plan)
```

- **`POST /chat`** — takes a `messages` list (the full conversation so far) and returns a `ConversationTurn` with the agent's next question, collected facts, and a `complete` flag. The caller holds all state; nothing is stored server-side.
- **`POST /plan`** — takes a `situation` string and optional `user_context` (e.g. the `collected_facts` from `/chat` once complete) and returns a full personalised plan.

### Modes

- **Local mode** (`LOCAL_MODE=true`): the backend POSTs directly to each agent's `/invocations` HTTP endpoint (`AGENT_URL` for the planner, `CHAT_AGENT_URL` for the conversation agent). This is the same contract whether the agent is a bare local process or running in a container — `BedrockAgentCoreApp.run()` serves it either way.
- **AgentCore mode** (`LOCAL_MODE=false`): the backend calls the deployed AgentCore runtimes via `boto3`'s `invoke_agent_runtime` (`AGENT_RUNTIME_ARN` / `CHAT_AGENT_RUNTIME_ARN`). Agent invocations can take well over a minute (real runs have taken 60–80s), so the client is configured with a longer read timeout and retries disabled.


## Local development

### 1. First-time setup

```bash
cp .env.example .env
```

Fill in `.env` as needed (see `.env.example` in the root dir):

```
LOCAL_MODE=true
AGENT_URL=http://agent:8080/invocations
CHAT_AGENT_URL=http://chat-agent:8080/invocations
```

`backend/log_utils.py` must be present — the app won't start without it. It's a separate copy from `agent/shared/log_utils.py` (the backend is a distinct deployable); if the logging interface changes, update both.

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

### 7. Send a request to the backend

**Planner** (`/plan`):
```bash
curl -X POST http://localhost:8000/plan \
  -H "Content-Type: application/json" \
  -d '{"situation": "I want to apply for tax-free childcare", "user_context": {"age": 31, "location": "London"}}'
```

`user_context` is optional. `situation` is required.

**Conversation agent** (`/chat`):
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role":"user","content":"I just had a baby and lost my job"}]}'
```

Or to simulate a multi turn conversation:

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
  "messages": [
    {"role":"user","content":"I just had a baby and lost my job"},
    {"role":"assistant","content":"First, a couple of key facts: your baby has been born now, yes? And roughly how long ago was the birth?"},
    {"role":"user","content":"Yes, born about 2 weeks ago"},
    {"role":"assistant","content":"Congratulations! And are you the birth mother, or the other parent? Also, will both parents be named on the birth certificate?"},
    {"role":"user","content":"I am the birth mother, and yes both parents will be on it"},
    {"role":"assistant","content":"Got it. In terms of your job loss — were you employed (rather than self-employed) before you lost the job, and do you know whether you were made redundant or left for another reason?"},
    {"role":"user","content":"I was employed and made redundant"},
    {"role":"assistant","content":"Thanks. A couple more: how old are you, and do you live in England?"},
    {"role":"user","content":"I am 29 and yes I live in England"},
    {"role":"assistant","content":"Had you been with that employer continuously for at least 2 years before the redundancy?"},
    {"role":"user","content":"Yes, just over 3 years"}
  ]
}'
```

Returns a `ConversationTurn` with `message` (next question), `collected_facts`, `outstanding`, and `complete`. Append the response as an `assistant` message and the user's answer as a `user` message, then POST again — repeating until `complete: true`. Pass `collected_facts` to `/plan` as `user_context`.

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
      - chat-agent
  ```

  With this, edits to `backend/app/*.py` take effect immediately without a
  rebuild or restart.


### 9. Shut down

```bash
docker compose down
```

## Testing against the deployed AgentCore runtimes

Once both runtimes are deployed and you have their ARNs, set in `.env`:

```
LOCAL_MODE=false
AGENT_RUNTIME_ARN=<planner runtime arn>
CHAT_AGENT_RUNTIME_ARN=<conversation runtime arn>
AWS_DEFAULT_REGION=eu-west-2
```

Run just the backend (no local agent containers needed):

```bash
docker compose up backend
```

Both `/plan` and `/chat` work unchanged; the backend routes each to its deployed runtime instead of the local HTTP call.
