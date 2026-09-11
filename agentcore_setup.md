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
│   │   ├── agentcore.ts    # AgentCoreProjectSpec types
│   │   ├── aws-targets.ts  # Deployment target types
│   │   └── mcp.ts          # Gateway and MCP tool types
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

The CLI is a global npm package — it lives on your machine, not inside the repo.

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

4. Navigate to Agentcore CLI project `cd PersonalisedPlanning`

5. Run in one terminal:
```bash
agentcore dev --logs
```

6. From another terminal send request:
```bash
agentcore dev "how do I get provisional driver's license?"
```

### Deploy agent

1. Configure AWS credentials using `gds cli`
2. Ensure the following env vars are defined in `.env` or terminal:
- `CLAUDE_CODE_USE_BEDROCK=1`
- `PLANNER_SECRET_ID=<secret_name>`
- `MCP_MODE=remote`

3. Navigate to Agentcore CLI project `cd PersonalisedPlanning`

4. Install CDK dependencies (run once, or whenever `agentcore/cdk/package.json` changes):
```bash
(cd agentcore/cdk && npm install)
```
Skipping this causes `agentcore deploy` to fail at the build step with `tsc: command not found`.

5.  Build and push the image locally first:
```bash
agentcore package --runtime planner
```

6. Deploy the CDK stack:
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
agentcore invoke --runtime planner "your prompt here"
```


## AgentCore Commands

| Command | Description |
| --- | --- |
| `agentcore create` | Create a new AgentCore project |
| `agentcore add` | Add resources (agent, memory, credential, gateway, evaluator, policy) |
| `agentcore remove` | Remove resources |
| `agentcore dev` | Run agent locally with hot-reload |
| `agentcore deploy` | Deploy to AWS via CDK |
| `agentcore status` | Show deployment status |
| `agentcore invoke` | Invoke agent (local or deployed) |
| `agentcore logs` | View agent logs |
| `agentcore traces` | View agent traces |
| `agentcore eval` | Run evaluations |
| `agentcore package` | Package agent artifacts |
| `agentcore validate` | Validate configuration |
| `agentcore pause` | Pause a deployed agent |
| `agentcore resume` | Resume a paused agent |
| `agentcore fetch` | Fetch remote resource definitions |
| `agentcore import` | Import existing resources |
| `agentcore update` | Check for CLI updates |

## Configuration

Edit the JSON files in `agentcore/` to configure your project. See `agentcore/.llm-context/` for type definitions and validation constraints.

The project uses a **flat resource model** — agents, memories, credentials, gateways, evaluators, and policies are top-level arrays in `agentcore.json`. Resources are independent; agents discover memories and credentials at runtime via environment variables or SDK calls.

## Resources

| Resource | Purpose |
| --- | --- |
| Agent (runtime) | HTTP, MCP, or A2A agent deployed to AgentCore Runtime |
| Memory | Persistent context storage with configurable strategies |
| Credential | API key or OAuth credential providers |
| Gateway | MCP gateway that routes tool calls to targets |
| Gateway Target | Tool implementation (Lambda, MCP server, OpenAPI, Smithy, API Gateway) |
| Evaluator | Custom LLM-as-a-Judge or code-based evaluation |
| Online Eval Config | Continuous evaluation pipeline for deployed agents |
| Policy | Cedar authorization policies for gateway tools |

### Agent Types

- **Template agents**: Created from framework templates (Strands, LangChain/LangGraph, GoogleADK, OpenAI Agents, Autogen)
- **BYO agents**: Bring your own code with `agentcore add agent --type byo`
- **Import agents**: Import existing Bedrock agents with `agentcore import`

### Build Types

- **CodeZip**: Python source packaged as a zip and deployed directly to AgentCore Runtime
- **Container**: Docker image built via CodeBuild (ARM64), pushed to ECR, and deployed to AgentCore Runtime

## Documentation

- [AgentCore CLI](https://github.com/aws/agentcore-cli)
- [AgentCore CDK Constructs](https://github.com/aws/agentcore-l3-cdk-constructs)
- [Amazon Bedrock AgentCore](https://aws.amazon.com/bedrock/agentcore/)
