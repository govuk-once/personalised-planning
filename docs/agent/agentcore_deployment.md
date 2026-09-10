# AgentCore Deployment: PersonalisedPlanning

## 1. Dependencies (`agent/app/pyproject.toml`)

Added `aws-opentelemetry-distro` — AgentCore's runtime validator requires it even though the CLI claims to handle OTEL automatically. Then ran `uv sync` to update `uv.lock`.

## 2. Build mode (`agentcore/agentcore.json`)

Used `Container` not `CodeZip`. CodeZip strips executable permissions from bundled binaries:

```json
"build": "Container"
```

## 3. Dockerfile

Placed in `agent/app/` alongside `main.py`. Key requirements:
- Fix permissions on the bundled Claude binary with `chmod`
- Run as non-root user — Claude automatically checks if the user is root to prevent running with `--dangerously-skip-permissions` setting
- Set `CLAUDE_CODE_USE_BEDROCK=1` — without this the SDK tries to use the Anthropic API directly instead of Bedrock

```dockerfile
FROM python:3.12-bookworm

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV CLAUDE_CODE_USE_BEDROCK=1

RUN apt-get update && apt-get -y install nodejs npm

COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --no-dev

COPY . .

RUN find . -name "claude" -type f | xargs chmod +x

RUN useradd -m -u 1000 agentuser
USER agentuser

EXPOSE 8080

CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
```

## 4. `.dockerignore`

Placed in `agent/app/` to prevent the local venv being copied into the image, which causes architecture mismatch errors (local ARM64 vs container x86_64):

```
.venv
__pycache__
*.pyc
.pytest_cache
.env
.env.local
```

## 5. Secrets Manager (`main.py`)

Hardcoded directly in order not rely on `.env` or environment variables to pass the secret name.

```python
load_dotenv()  # local development only
load_secrets_into_env("planner-agent", region="eu-west-2")
```

This works because `load_secrets_into_env` won't overwrite env vars already set, so local `.env` values still take precedence during development.

## 6. IAM permissions (manual step — to be baked into CDK)

After every fresh stack deploy the runtime role needs `secretsmanager:GetSecretValue`. The role name changes on each deploy so fetch it first:

```bash
aws iam list-roles --query "Roles[?contains(RoleName, 'PersonalisedPla') && contains(RoleName, 'Ru')].RoleName" --output text
```

Then attach the policy:

```bash
aws iam put-role-policy \
  --role-name <runtime-role-name> \
  --policy-name AllowPlannerSecretAccess \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Action": "secretsmanager:GetSecretValue",
      "Resource": "arn:aws:secretsmanager:eu-west-2:<account-id>:secret:planner-agent*"
    }]
  }'
```

## 7. Structured output parsing

The SDK wraps `StructuredOutput` tool results in a double `result` key. To handle parsing errors, result block is unwrapped twice:

```python
result = block.input.get("result", {}).get("result")
```

---

## Redeploying after code-only changes

`agentcore deploy` uses content-addressed CDK asset caching. If no tracked file has changed, it reuses the cached ZIP from S3 and CodeBuild won't pick up your changes.

**Preferred approach**, use `agentcore package` first to build image locally. Docker needs to be running:
```bash
agentcore package --runtime planner
agentcore deploy
```

**Alternative approach**, touch any `.py` file before deploying:

```bash
echo "# redeploy $(date)" >> agent/app/main.py
agentcore deploy
```

---

## Outstanding

- Bake the Secrets Manager IAM policy into the CDK stack so it survives redeployments automatically

## To test run
1. Check out branch
2. Authenticate with GDS CLI to obtain AWS credentials
3. `cd PersonalisedPlanning`
4. `agentcore package --runtime planner` — build and push the image locally first
5. `agentcore deploy` — deploy the CDK stack
6. Attach the Secrets Manager IAM policy (manual step until it's baked into CDK) if running for the first time or completely recreating the stack:

```bash
aws iam list-roles --query "Roles[?contains(RoleName, 'PersonalisedPla') && contains(RoleName, 'Ru')].RoleName" --output text
aws iam put-role-policy --role-name <role-name> --policy-name AllowPlannerSecretAccess --policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":"secretsmanager:GetSecretValue","Resource":"arn:aws:secretsmanager:eu-west-2:<account-id>:secret:planner-agent*"}]}'
```

7. `agentcore invoke --runtime planner --prompt "your prompt here"`
