#!/bin/bash
# Codex SessionStart hook: if today's report is missing, inject a one-time
# startup instruction for Codex to run the daily news skill.

set -u

TODAY=$(date +%Y-%m-%d)
NEWS_DIR="$HOME/Plan/news"
OUTPUT="$NEWS_DIR/$TODAY.md"
LOG="$NEWS_DIR/news_log.txt"

mkdir -p "$NEWS_DIR"

append_log() {
    (echo "$1" >> "$LOG") 2>/dev/null || true
}

# Treat the generated markdown file as the source of truth. A previous
# "triggered" log entry is not enough; the skill may not have completed.
if [ -s "$OUTPUT" ]; then
    if ! grep -q "^$TODAY done" "$LOG" 2>/dev/null; then
        append_log "$TODAY done (existing file)"
    fi
    exit 0
fi

append_log "$TODAY requested"

python3 - "$TODAY" "$OUTPUT" <<'PY'
import json
import sys

today = sys.argv[1]
output = sys.argv[2]
message = (
    f"Daily tech news for {today} has not been generated yet. "
    "Before handling the user's next request, invoke the my_news_daily skill once "
    f"to generate and format {output}. If that file appears before you act, skip this."
)

print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": message,
    }
}, ensure_ascii=False))
PY
