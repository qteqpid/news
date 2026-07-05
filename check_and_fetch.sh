#!/bin/bash
# Codex SessionStart hook: if today's reports are missing, inject one-time
# startup instructions for Codex to run the combined daily news/app-ideas skill.

set -u

TODAY=$(date +%Y-%m-%d)
NEWS_DIR="$HOME/my_repos/news/ai"
OUTPUT="$NEWS_DIR/$TODAY.md"
NEWS_JSON="$NEWS_DIR/$TODAY.json"
LOG="$NEWS_DIR/news_log.txt"
APP_DIR="$HOME/my_repos/news/app"
APP_OUTPUT="$APP_DIR/$TODAY.md"
APP_JSON="$APP_DIR/$TODAY.json"
REDDIT_DIR="$HOME/my_repos/news/reddit"
REDDIT_JSON="$REDDIT_DIR/$TODAY.json"

mkdir -p "$NEWS_DIR" "$APP_DIR" "$REDDIT_DIR"

append_log() {
    (echo "$1" >> "$LOG") 2>/dev/null || true
}

NEEDS_NEWS=0
NEEDS_APP=0
NEEDS_REDDIT=0

# Treat generated markdown/json files as the source of truth. A previous
# "triggered" log entry is not enough; a skill may not have completed.
if [ -s "$OUTPUT" ] && [ -s "$NEWS_JSON" ]; then
    if ! grep -q "^$TODAY done" "$LOG" 2>/dev/null; then
        append_log "$TODAY done (existing file)"
    fi
else
    NEEDS_NEWS=1
    append_log "$TODAY requested"
fi

if [ -s "$APP_OUTPUT" ] && [ -s "$APP_JSON" ]; then
    if ! grep -q "^$TODAY app done" "$LOG" 2>/dev/null; then
        append_log "$TODAY app done (existing file)"
    fi
else
    NEEDS_APP=1
    append_log "$TODAY app requested"
fi

if [ -s "$REDDIT_JSON" ]; then
    if ! grep -q "^$TODAY reddit done" "$LOG" 2>/dev/null; then
        append_log "$TODAY reddit done (existing file)"
    fi
else
    NEEDS_REDDIT=1
    append_log "$TODAY reddit requested"
fi

if [ "$NEEDS_NEWS" -eq 0 ] && [ "$NEEDS_APP" -eq 0 ] && [ "$NEEDS_REDDIT" -eq 0 ]; then
    exit 0
fi

python3 - "$TODAY" "$OUTPUT" "$NEWS_JSON" "$NEEDS_NEWS" "$APP_OUTPUT" "$APP_JSON" "$NEEDS_APP" "$REDDIT_JSON" "$NEEDS_REDDIT" <<'PY'
import json
import sys

today = sys.argv[1]
news_output = sys.argv[2]
news_json = sys.argv[3]
needs_news = sys.argv[4] == "1"
app_output = sys.argv[5]
app_json = sys.argv[6]
needs_app = sys.argv[7] == "1"
reddit_json = sys.argv[8]
needs_reddit = sys.argv[9] == "1"

messages = []
missing = []
if needs_news:
    missing.append(f"daily tech news outputs ({news_output}, {news_json})")
if needs_app:
    missing.append(f"daily app inspiration outputs ({app_output}, {app_json})")
if needs_reddit:
    missing.append(f"daily Reddit app-idea output ({reddit_json})")

messages.append(
    f"Daily combined news/app/reddit report for {today} is incomplete: "
    + "; ".join(missing)
    + ". Before handling the user's next request, invoke the my-daily-news-and-app-ideas skill once if news/app Markdown or JSON outputs are missing, "
    + "and run `python3 ~/my_repos/news/fetch_reddit.py` if the Reddit JSON is missing. "
    + "If fetch_reddit.py reports that no Reddit browser export exists, first run `cd ~/my_repos/reddit-app-idea-miner && python3 scripts/collect_routes.py --browser chrome`, then rerun fetch_reddit.py; "
    + "do not commit or push because git sync is handled by the scheduled launchd task. "
    + "Before writing final news or app outputs, dedupe against previous dates: use `python3 ~/my_repos/news/fetch_news.py --seen-keys news` for tech-news article/project/post keys, "
    + "and `python3 ~/my_repos/news/fetch_news.py --seen-keys app` for prior app-idea titles/source keys; skip repeats instead of carrying them into the new report. "
    + "Use `APP` as the source name for app-related generated items/signals. "
    + "The Reddit output must be a flat JSON array under `news/reddit/YYYY-MM-DD.json` with only title, summary, url, and source fields. "
    + "For app ideas, use the App Store gold-app heuristics: high demand with low rating, stale incumbents, "
    + "platform gaps, country gaps, and keyword supply gaps. If all expected files appear before you act, skip this."
)

print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": "\n\n".join(messages),
    }
}, ensure_ascii=False))
PY
