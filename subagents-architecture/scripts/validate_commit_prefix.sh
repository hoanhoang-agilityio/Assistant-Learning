#!/usr/bin/env bash
set -euo pipefail

msg_file="${1:?commit message file required}"
msg="$(head -n1 "$msg_file")"

if [[ "$msg" =~ ^Merge ]]; then
  exit 0
fi

pattern='^(feat|fix|docs|style|refactor|perf|test|chore|ci|build|revert)(\([a-z0-9._-]+\))?: .+'
if [[ ! "$msg" =~ $pattern ]]; then
  echo "precheck: commit message must use a conventional prefix" >&2
  echo "  Example: feat: add planning subgraph" >&2
  echo "  Allowed: feat, fix, docs, style, refactor, perf, test, chore, ci, build, revert" >&2
  exit 1
fi
