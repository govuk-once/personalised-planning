# personalised-planning
Helping users plan through complex situations in life

## Status

**Experimental prototype.** This is exploratory work, not a live service and not production-ready.
It is published in the open under
[Service Standard point 12](https://www.gov.uk/service-manual/service-standard/point-12-make-new-source-code-open)
so others can learn from it and reuse it. Expect breaking changes, and do not deploy it as-is.

## Licence

Licensed under the [MIT Licence](LICENSE). © Crown Copyright (Government Digital Service).

## Security

See [SECURITY.md](SECURITY.md) for how to report a vulnerability.

## Features

- **Python 3.12+** with [uv](https://github.com/astral-sh/uv) for fast dependency management
- **Pre-commit hooks** for code quality and security:
  - Python linting and formatting with Ruff
  - Secret detection with detect-secrets
  - End-of-file and trailing whitespace fixes
  - YAML/JSON validation
  - Docker linting with hadolint
- **AWS integration** including Bedrock for LLM calls
- **Docker support** for local testing and cloud deployment

## Prerequisites

- Python 3.12 or 3.13
- [uv](https://github.com/astral-sh/uv) for dependency management
- [pre-commit](https://pre-commit.com/) for git hooks
- Docker (optional, for containerization)
- AWS credentials (optional, for AWS services)

## Getting Started

### 1. Install Dependencies

Install uv (macOS with Homebrew):
```bash
brew install uv
```

Or use pip:
```bash
pip install uv
```

See [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/) for other methods.


Install project dependencies:
```bash
uv sync --extra dev
```

### 2. Set Up Pre-commit Hooks

Install pre-commit hooks:
```bash
uv run pre-commit install
```

Run hooks manually on all files:
```bash
uv run pre-commit run --all-files
```
