FROM python:3.12-slim-bookworm

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PATH="/home/agentuser/.local/bin:$PATH"

# uv bundles its own CA certs by default and ignores the system
# trust store, so it won't trust the corporate proxy CA installed
# below unless told to use system certs instead.
ENV UV_SYSTEM_CERTS=1

# Install ca-certificates and trust the corporate proxy's root CA
# so HTTPS calls out of this build (pip, uv, etc.) don't fail on
# SSL inspection. Cert is fetched from our repo rather than
# copied in locally, so it's a single source of truth shared across
# services and doesn't need to be exported/committed manually.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && curl -fsSL --proto '=https' --tlsv1.2 -o /usr/local/share/ca-certificates/zscaler-root-ca.crt \
       https://raw.githubusercontent.com/alphagov/govuk-infrastructure/refs/heads/main/cacerts/zscaler-root-ca.pem \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 agentuser

COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --no-dev && chown -R agentuser:agentuser /app/.venv

COPY . .

USER agentuser

EXPOSE 8080
CMD ["uv", "run", "--no-sync", "opentelemetry-instrument", "python", "main.py"]
# CMD ["uv", "run", "--no-sync", "opentelemetry-instrument", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
