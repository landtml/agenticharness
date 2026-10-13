#!/usr/bin/env bash
# Prepares a Claude Code cloud session so agents can run `make check` right away.
set -euo pipefail
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi
cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/..}"
make setup >/dev/null
