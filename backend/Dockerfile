# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:0.13.1-python3.12-trixie-slim AS builder
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app

# Dependencies first so source edits don't invalidate this layer.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-dev --no-install-project

COPY pyproject.toml uv.lock ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable


FROM python:3.12.15-slim-trixie AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    PORT=8000 \
    ENVIRONMENT=prod

RUN groupadd --system --gid 10001 ursache \
    && useradd --system --uid 10001 --gid ursache --home-dir /app --no-create-home ursache
WORKDIR /app
COPY --from=builder --chown=ursache:ursache /app/.venv /app/.venv

USER ursache
EXPOSE 8000
# Render sets $PORT; proxy headers make slowapi see the client IP, not Render's proxy.
CMD ["sh", "-c", "exec uvicorn ursache.api.main:create_app --factory --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
