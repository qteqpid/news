#!/bin/bash
# Codex SessionStart hook: if today's reports are missing, inject one-time
# startup instructions for Codex to run only the missing daily report processes.

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
MINER_DIR="${REDDIT_APP_IDEA_MINER_DIR:-$HOME/my_repos/reddit-app-idea-miner}"
REDDIT_EXPORT="$MINER_DIR/exports/reddit-route-export-$TODAY.json"

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

if [ -s "$REDDIT_JSON" ] && [ -s "$REDDIT_EXPORT" ]; then
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

python3 - "$TODAY" "$OUTPUT" "$NEWS_JSON" "$NEEDS_NEWS" "$APP_OUTPUT" "$APP_JSON" "$NEEDS_APP" "$REDDIT_JSON" "$REDDIT_EXPORT" "$NEEDS_REDDIT" <<'PY'
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
reddit_export = sys.argv[9]
needs_reddit = sys.argv[10] == "1"

messages = []
missing = []
if needs_news:
    missing.append(f"daily tech news outputs ({news_output}, {news_json})")
if needs_app:
    missing.append(f"daily app inspiration outputs ({app_output}, {app_json})")
if needs_reddit:
    missing.append(f"daily Reddit app-idea output/fresh export ({reddit_json}, {reddit_export})")

processes = []
if needs_news:
    processes.append(
        "AI process: first re-check that both tech-news outputs are still missing or incomplete. "
        "If either is missing, run `python3 ~/my_repos/news/fetch_news.py --seen-keys news` for prior article/project/post keys, "
        "then run the AI news fetch/organize process and write only `news/ai/YYYY-MM-DD.md` and `news/ai/YYYY-MM-DD.json`. "
        "Skip repeats from prior dates."
    )
if needs_app:
    processes.append(
        "App process: first re-check that both app outputs are still missing or incomplete. "
        "If either is missing, run `python3 ~/my_repos/news/fetch_news.py --seen-keys app` for prior app-idea titles/source keys, "
        "then run only the app inspiration gather/organize process and write only `news/app/YYYY-MM-DD.md` and `news/app/YYYY-MM-DD.json`. "
        "Use `APP` as the source name for app-related generated items/signals, and apply the App Store gold-app heuristics: high demand with low rating, stale incumbents, platform gaps, country gaps, and keyword supply gaps."
    )
if needs_reddit:
    processes.append(
        "Reddit process: first re-check that both the Reddit JSON and the fresh dated browser export are present. "
        "If either is missing, run `python3 ~/my_repos/news/fetch_reddit.py`. "
        "fetch_reddit.py must use a fresh dated browser export for the target date; by default it auto-runs `scripts/collect_routes.py --browser chrome --hydrate-details` when today's export is missing and never silently reuses an older export. "
        "The Reddit output must be a flat JSON array under `news/reddit/YYYY-MM-DD.json` with only title, summary, url, and source fields."
    )

messages.append(
    f"Daily report outputs for {today} are incomplete: "
    + "; ".join(missing)
    + ". Before handling the user's next request, run the missing processes independently and in this order: "
    + " ".join(processes)
    + " Do not rerun completed processes: if AI outputs already exist, skip AI; if app outputs already exist, skip app; if both Reddit output and the fresh dated export already exist, skip Reddit. "
    + "Do not commit or push because git sync is handled by the scheduled launchd task. "
    + "If all expected files appear before you act, skip this."
)

print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": "\n\n".join(messages),
    }
}, ensure_ascii=False))
PY
