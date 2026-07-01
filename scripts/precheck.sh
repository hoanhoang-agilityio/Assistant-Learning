#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if [ "$#" -eq 0 ]; then
  exit 0
fi

uv run ruff format "$@"
uv run ruff check --fix --unsafe-fixes "$@"
