#!/bin/sh
# Applies migrations before starting, when asked to.
#
# Opt-in rather than automatic: concurrent replicas all running `alembic upgrade head` on
# boot race each other. Compose sets RUN_MIGRATIONS=true for local development; a real
# deployment runs the migration as its own step.
set -e

if [ "${RUN_MIGRATIONS}" = "true" ]; then
    echo "running migrations"
    alembic upgrade head
fi

exec "$@"
