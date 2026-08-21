# syntax=docker/dockerfile:1

# Two stages rather than the reference's one: build-essential and uv are only needed to
# resolve the virtualenv, and this image is already large because llm-guard pulls torch.
FROM python:3.13.2-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && pip install --upgrade pip \
    && pip install uv \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Locked dependencies first, so this layer survives any source-only change.
# README.md is copied because pyproject declares it as the project readme.
# NOTE: on linux/amd64 PyPI's torch wheel bundles the CUDA runtime and adds several GB.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project --no-dev

COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./
RUN uv sync --frozen --no-dev


FROM python:3.13.2-slim AS runtime

ARG APP_ENV=production

ENV APP_ENV=${APP_ENV} \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONFAULTHANDLER=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random \
    PYTHONDONTWRITEBYTECODE=1

RUN useradd -m appuser

WORKDIR /app

COPY --from=builder --chown=appuser:appuser /app/.venv ./.venv
COPY --from=builder --chown=appuser:appuser /app/src ./src
COPY --from=builder --chown=appuser:appuser /app/alembic ./alembic
COPY --from=builder --chown=appuser:appuser /app/alembic.ini ./
COPY --chown=appuser:appuser docker/entrypoint.sh /app/scripts/entrypoint.sh

RUN chmod +x /app/scripts/entrypoint.sh && mkdir -p /app/logs && chown appuser:appuser /app/logs

USER appuser

EXPOSE 8000

# urllib rather than curl: slim carries no curl, and the health route sits behind API_V1_STR.
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health').read()"

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
