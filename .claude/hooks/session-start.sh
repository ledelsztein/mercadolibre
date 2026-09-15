#!/bin/bash
set -uo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/session-start.py"
exit 0
