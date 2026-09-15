# syntax=docker/dockerfile:1

FROM python:3.13-slim AS runtime

COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /uvx /usr/local/bin/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    MEMORY_CONFIG_PATH=/app/config/memory.json \
    MEMORY_ADMIN_API_ENABLED=false \
    PORT=8001

WORKDIR /app

RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /app/config

COPY pyproject.toml uv.lock README.md README.zh.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY deploy/render/memory.json ./config/memory.json
RUN uv sync --frozen --no-dev

USER appuser

EXPOSE 8001

CMD ["personal-agent-memory-http"]
