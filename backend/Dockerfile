FROM python:3.12-slim

WORKDIR /app

# uv bundles its own CA certs by default and ignores the system
# trust store, so it won't trust the corporate proxy CA installed
# below unless told to use system certs instead.
ENV UV_SYSTEM_CERTS=1

# Install ca-certificates and trust the corporate proxy's root CA
# so HTTPS calls out of this build (pip, uv, etc.) don't fail on
# SSL inspection. Cert is fetched from our repo rather than
# copied in locally, so it's a single source of truth shared across
# services and doesn't need to be exported/committed manually.
# Create non-root user before any files are copied — this is a slim,
# file-free layer, so it adds negligible size.
# uv gives us fast, reproducible installs from pyproject.toml/uv.lock
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && curl -fsSL --proto '=https' --tlsv1.2 -o /usr/local/share/ca-certificates/zscaler-root-ca.crt \
       https://raw.githubusercontent.com/alphagov/govuk-infrastructure/refs/heads/main/cacerts/zscaler-root-ca.pem \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system app && useradd --system --gid app --create-home --uid 1000 app \
    && pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project && chown -R app:app /app/.venv

COPY app ./app
COPY log_utils.py .
COPY agent_mock_response.py .

USER app

EXPOSE 8000

CMD ["uv", "run", "--frozen", "--no-dev", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
