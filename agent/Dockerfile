FROM python:3.12-slim-bookworm
WORKDIR /app
ENV PYTHONUNBUFFERED=1
ENV PATH="/home/agentuser/.local/bin:$PATH"
# shared/ lives at /app; make it importable from either agent subdir (app/, chat/)
ENV PYTHONPATH=/app

RUN useradd -m -u 1000 agentuser

COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --no-dev && chown -R agentuser:agentuser /app/.venv

COPY . .

USER agentuser

# Run from the planner subdir so relative reads (./system_prompt.md) resolve;
# uv discovers the project + .venv by walking up to /app.
WORKDIR /app/app

EXPOSE 8080
CMD ["uv", "run", "--no-sync", "opentelemetry-instrument", "python", "main.py"]
