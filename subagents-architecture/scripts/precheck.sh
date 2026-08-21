#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

if [ "$#" -eq 0 ]; then
  exit 0
fi

# Pre-commit passes paths relative to the git root. This script cds into the
# project directory, so strip that prefix when the two roots differ.
git_root="$(git rev-parse --show-toplevel)"
prefix="${project_root#"$git_root"/}"
if [ "$prefix" = "$project_root" ]; then
  prefix=""
else
  prefix="$prefix/"
fi

files=()
for path in "$@"; do
  files+=("${path#"$prefix"}")
done

uv run ruff format "${files[@]}"
uv run ruff check --fix --unsafe-fixes "${files[@]}"
