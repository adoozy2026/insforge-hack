# Multi-arch Playwright-Python base — already includes Chromium, the
# matching browser deps, and a sane Python toolchain.
FROM mcr.microsoft.com/playwright/python:v1.60.0-noble

WORKDIR /app

# uv is the package manager we use locally; we install it system-wide so the
# image build matches the dev environment.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && curl -LsSf https://astral.sh/uv/install.sh | sh \
    && ln -s /root/.local/bin/uv /usr/local/bin/uv

# Dependency layer caches well: copy lockfile alone, sync, then copy app.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy the rest of the orchestrator. Anything in .dockerignore is excluded.
COPY app ./app
COPY README.md ./

# uv writes a venv at /app/.venv; put its bin first on PATH.
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8787

EXPOSE 8787

# Single-process uvicorn. The pipeline is async-native and the poller runs in
# the FastAPI lifespan, so adding workers would just multiply the polling.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
