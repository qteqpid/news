#!/bin/bash
# Codex SessionStart hook: if today's reports are missing, inject one-time
# startup instructions for Codex to run the daily news/app-ideas skills.

set -u

TODAY=$(date +%Y-%m-%d)
NEWS_DIR="$HOME/Plan/news"
OUTPUT="$NEWS_DIR/$TODAY.md"
LOG="$NEWS_DIR/news_log.txt"
APP_DIR="$HOME/my_repos/news/app"
APP_OUTPUT="$APP_DIR/$TODAY.md"

mkdir -p "$NEWS_DIR" "$APP_DIR"

append_log() {
    (echo "$1" >> "$LOG") 2>/dev/null || true
}

NEEDS_NEWS=0
NEEDS_APP=0

# Treat generated markdown files as the source of truth. A previous
# "triggered" log entry is not enough; a skill may not have completed.
if [ -s "$OUTPUT" ]; then
    if ! grep -q "^$TODAY done" "$LOG" 2>/dev/null; then
        append_log "$TODAY done (existing file)"
    fi
else
    NEEDS_NEWS=1
    append_log "$TODAY requested"
fi

if [ -s "$APP_OUTPUT" ]; then
    if ! grep -q "^$TODAY app done" "$LOG" 2>/dev/null; then
        append_log "$TODAY app done (existing file)"
    fi
else
    NEEDS_APP=1
    append_log "$TODAY app requested"
fi

if [ "$NEEDS_NEWS" -eq 0 ] && [ "$NEEDS_APP" -eq 0 ]; then
    exit 0
fi

python3 - "$TODAY" "$OUTPUT" "$NEEDS_NEWS" "$APP_OUTPUT" "$NEEDS_APP" <<'PY'
import json
import sys

today = sys.argv[1]
news_output = sys.argv[2]
needs_news = sys.argv[3] == "1"
app_output = sys.argv[4]
needs_app = sys.argv[5] == "1"

messages = []
if needs_news:
    messages.append(
        f"Daily tech news for {today} has not been generated yet. "
        "Before handling the user's next request, invoke the my_news_daily skill once "
        f"to generate and format {news_output}. If that file appears before you act, skip this."
    )
if needs_app:
    messages.append(
        f"Daily app inspiration for {today} has not been generated yet. "
        "Before handling the user's next request, invoke the my-app-ideas-daily skill once "
        f"to fetch current app opportunity signals and save {app_output}. "
        "Use the App Store gold-app heuristics: high demand with low rating, stale incumbents, "
        "platform gaps, country gaps, and keyword supply gaps. If that file appears before you act, skip this."
    )

print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": "\n\n".join(messages),
    }
}, ensure_ascii=False))
PY
