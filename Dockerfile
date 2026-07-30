# Production image for the PT AI Core API.
#
# Two stages so the build toolchain and the lockfile resolution never reach the
# runtime layer. The runtime stage carries the virtualenv and the installed
# package only.
#
# Deliberately installs *without* the `eval` extra: ragas/datasets/pandas/pyarrow
# are ~180 MB and are only needed by the benchmarks (see pyproject.toml). Enabling
# VERIFICATION_USE_REAL_RAGAS or VERIFICATION_PRODUCTION_USE_REAL_RAGAS in a
# container built this way will fail on import -- build with
# `--build-arg EXTRAS="--extra eval"` if you need those paths.

# ---------------------------------------------------------------- build stage
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

ARG EXTRAS=""

# Resolve dependencies before copying source, so editing application code does
# not invalidate the (slow) dependency layer.
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev ${EXTRAS}

COPY src/ ./src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev ${EXTRAS}

# -------------------------------------------------------------- runtime stage
FROM python:3.12-slim AS runtime

# curl is needed by HEALTHCHECK below; nothing else is added.
RUN apt-get update \
    && apt-get install --no-install-recommends -y curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 appuser

WORKDIR /app

COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appuser /app/src /app/src

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Runtime artifacts go to a writable volume, never into the source tree --
    # this is what lets /app/src stay read-only.
    WORKSPACE_ROOT=/var/lib/pt-ai/workspace \
    LOG_FORMAT=json \
    LOG_LEVEL=INFO

RUN mkdir -p /var/lib/pt-ai/workspace && chown -R appuser:appuser /var/lib/pt-ai

USER appuser
VOLUME ["/var/lib/pt-ai/workspace"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
