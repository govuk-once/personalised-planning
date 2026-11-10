# AgentCore Project

This project was created with the [AgentCore CLI](https://github.com/aws/agentcore-cli).

## Project Structure

```
my-project/
├── AGENTS.md               # AI coding assistant context
├── agentcore/
│   ├── agentcore.json      # Project config (agents, memories, credentials, gateways, evaluators)
│   ├── aws-targets.json    # Deployment targets (account + region)
│   ├── .env.local          # Secrets — API keys (gitignored)
│   ├── .llm-context/       # TypeScript type definitions for AI assistants
│   │   ├── agentcore.ts    # AgentCoreProjectSpec types (including gateways)
│   │   └── aws-targets.ts  # Deployment target types
│   └── cdk/                # CDK infrastructure (@aws/agentcore-cdk)
├── app/                    # Agent application code
└── evaluators/             # Custom evaluator code (if any)
```

## Key Files

Here are key agent application files:

| File | Purpose |
|---|---|
| `agentcore/agentcore.json` | AgentCore project config — defines agent name, code location, entrypoint, runtime version |
| `agent/app/main.py` | AgentCore entrypoint — `BedrockAgentCoreApp` + `@app.entrypoint` |
| `agent/app/planner_agent.py` | Claude SDK client — MCP config, tool handling, structured output parsing |
| `agent/app/planner_logic.py` | Core logic — shared between local and deployed entrypoints |
| `agent/app/structured_outputs.py` | Pydantic schemas — `FirstStep`, `Plan`, `AgentHelp`, `LLMResult` |
| `agent/app/system_prompt.md` | Agent instructions — tool usage, eligibility signal rules, output format |
| `agent/app/.env` | Local secrets — gitignored, must be created manually |
| `agent/app/pyproject.toml` | Python dependencies — always edit via `uv add` from this directory |

## Getting Started

### Prerequisites

- **Node.js** 20.x or later
- **Python 3.12+** and **uv** for Python agents ([install uv](https://docs.astral.sh/uv/getting-started/installation/))
- **AWS credentials** configured via `gds cli`
- **Docker**
- **npm** — comes with Node.js
- **Homebrew** — for installing pyenv

### Initial set up
1. Install Python 3.12 via pyenv

The AgentCore CLI requires Python 3.10+. The project uses 3.12.

```bash
brew install pyenv
```

Add pyenv to your shell (`~/.zshrc`):

```bash
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"
```

Reload your shell:

```bash
source ~/.zshrc
```

Install Python 3.12:

```bash
pyenv install 3.12
```

The repo root already has a `.python-version` file set to `3.12` — no further configuration needed.

---

2. Install the AgentCore CLI

The CLI is a global npm package — it lives on your machine, not inside the repo. This project uses CLI v1 (`agentcore --version` should print 1.x). To upgrade an existing install, run `agentcore update`.

```bash
npm install -g @aws/agentcore
agentcore --version
```
---

3. Set Up the Python Environment

> **Important:** Always run `uv` commands from inside `PersonalisedPlanning/agent/app/`. Running from any other directory will install dependencies into the wrong virtual environment.

```bash
cd ~/personalised-planning/PersonalisedPlanning/agent/app
uv venv
uv sync
```

To add a new dependency:

```bash
cd ~/personalised-planning/PersonalisedPlanning/agent/app
uv add <package-name>
```

Install node.js dependencies for CDK
```bash
cd PersonalisedPlanning/agentcore/cdk
npm install
```

---

4. Create `agentcore/aws-targets.json`

Note that: `gds-cli aws <role> -d` prints the account number:

```json
[
  {
    "name": "default",
    "description": "Default target (eu-west-2)",
    "account": "<aws-account-id>",
    "region": "eu-west-2"
  }
]
```

### Run agent locally

1. Configure AWS credentials using `gds cli`
2. Ensure the following env vars are defined in `.env` or terminal:
- `CLAUDE_CODE_USE_BEDROCK=1`
- `PLANNER_SECRET_ID=<secret_name>`
- `MCP_MODE=local`
- `GRAPH_SERVER_PATH=/abs_path_to/personalised_planning/mcp-servers/service-graph`

3. To ensure service graph mcp-server has necessary dependencies installed, run once:
```bash
cd mcp-servers/service-graph
npm install
```

4. Navigate to the repo root (the directory containing `agentcore/`)

5. Run the planner in one terminal (it prints the runtime's output):
```bash
agentcore dev --agent planner
```
To run the conversation agent alongside it, use another terminal and another port: `agentcore dev --agent conversation --port 8081`.

6. From another terminal send a request:
```bash
agentcore invoke --runtime planner --local --payload '{"prompt": "how do I get provisional driver'\''s license?"}'

# Conversation agent (if started on port 8081)
agentcore invoke --runtime conversation --local --port 8081 --payload '{"messages": [{"role":"user","content":"I want to learn to drive"}]}'
```

### Deploy agent

1. Configure AWS credentials using `gds cli`
2. Ensure the following env vars are defined in `.env` or terminal:
- `CLAUDE_CODE_USE_BEDROCK=1`
- `PLANNER_SECRET_ID=<secret_name>`
- `MCP_MODE=remote`

3. Navigate to the repo root (the directory containing `agentcore/`)

4. Install CDK dependencies (run once, or whenever `agentcore/cdk/package.json` changes):
```bash
(cd agentcore/cdk && npm install)
```
Skipping this causes `agentcore build` to fail with `tsc: command not found`.

5. Build the project. This validates `agentcore.json` and synthesizes the CDK app into `agentcore/cdk/cdk.out`, catching config errors before anything touches AWS:
```bash
agentcore build
```

6. Deploy the stack. The container images for both runtimes are built in AWS by CodeBuild, so no local Docker build or push is needed:
```bash
agentcore deploy
```

7. Attach the Secrets Manager IAM policy (manual step until it's baked into CDK) if running for the first time or completely recreating the stack:
```bash
aws iam list-roles --query "Roles[?contains(RoleName, 'PersonalisedPla') && contains(RoleName, 'Ru')].RoleName" --output text
aws iam put-role-policy --role-name <role-name> --policy-name AllowPlannerSecretAccess --policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":"secretsmanager:GetSecretValue","Resource":"arn:aws:secretsmanager:eu-west-2:<account-number>:secret:planner-agent*"}]}'
```

8. Send prompt:
```bash
agentcore invoke --runtime planner --payload '{"prompt": "your prompt here"}'
```

9. Check the logs:
```bash
agentcore logs runtime --name planner --since 15m
```


## AgentCore Commands (CLI v1)

| Command | Description |
| --- | --- |
| `agentcore create` | Create a new AgentCore project |
| `agentcore add <resource>` | Add resources (runtime, memory, credentials, gateway, evaluator, policy, harness, …) |
| `agentcore remove <resource> --name <name>` | Remove a resource |
| `agentcore dev --agent <runtime>` | Run a runtime locally |
| `agentcore build` | Validate the project and synthesize the CDK app |
| `agentcore deploy` | Deploy to AWS via CDK (run after `agentcore build`) |
| `agentcore status` | Show deployed resources and their ARNs |
| `agentcore invoke --runtime <runtime> --payload '<json>'` | Invoke a runtime (`--local` for the dev server) |
| `agentcore logs runtime --name <runtime>` | Search or tail (`--tail`) runtime logs |
| `agentcore traces` | View traces |
| `agentcore runtime <subcommand>` | Inspect deployed runtimes: `get`, `list`, `version`, `endpoint`, `shell`, `exec` |
| `agentcore eval <subcommand>` | Evaluators, online evals, datasets, batch evaluations, A/B tests |
| `agentcore export` | Convert project resources into editable code you own |
| `agentcore migrate` | Migrate a v0 project to the v1 format (already done for this repo) |
| `agentcore update` | Check for and install CLI updates |

Run `agentcore <command> --help` for each command's options.

## Configuration

Edit the JSON files in `agentcore/` to configure your project. See `agentcore/.llm-context/` for type definitions and validation constraints.

The project uses a **flat resource model** — runtimes, memories, credentials, gateways, evaluators, and policies are top-level arrays in `agentcore.json`. Resources are independent; agents discover memories and credentials at runtime via environment variables or SDK calls.

## Resources

| Resource | Purpose |
| --- | --- |
| Runtime | HTTP, MCP, or A2A agent deployed to AgentCore Runtime |
| Harness | Config-defined agent (`harness.yaml`) managed by AgentCore |
| Memory | Persistent context storage with configurable strategies |
| Credential | API key or OAuth credential providers |
| Gateway | MCP gateway that routes tool calls to targets |
| Gateway Target | Tool implementation (Lambda, MCP server, OpenAPI, Smithy, API Gateway) |
| Evaluator | Custom LLM-as-a-Judge or code-based evaluation |
| Online Eval Config | Continuous evaluation pipeline for deployed agents |
| Policy | Cedar authorization policies for gateway tools |

### Agent Types

- **Runtimes**: your own agent code, added with `agentcore add runtime` (both agents in this project are runtimes)
- **Harnesses**: config-defined agents, added with `agentcore add harness`

### Build Types

- **CodeZip**: Python source packaged as a zip and deployed directly to AgentCore Runtime
- **Container**: Docker image built via CodeBuild (ARM64), pushed to ECR, and deployed to AgentCore Runtime

## Documentation

- [AgentCore CLI](https://github.com/aws/agentcore-cli)
- [AgentCore CDK Constructs](https://github.com/aws/agentcore-l3-cdk-constructs)
- [Amazon Bedrock AgentCore](https://aws.amazon.com/bedrock/agentcore/)
