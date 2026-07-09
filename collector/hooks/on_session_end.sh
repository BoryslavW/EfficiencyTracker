#!/bin/bash
# Claude Code SessionEnd hook — auto-harvest the just-ended session.
# Receives JSON on stdin with session_id and transcript_path.

INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null)

if [ -z "$SESSION_ID" ]; then
  exit 0
fi

HARVESTER="$(dirname "$0")/../session_harvester.py"

python3 "$HARVESTER" --auto-harvest "$SESSION_ID" >> /tmp/session_harvester.log 2>&1 &
