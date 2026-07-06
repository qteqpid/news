#!/bin/bash
# Codex SessionStart hook: delegate daily report checks to the news pipeline.

set -u

NEWS_ROOT="$HOME/my_repos/news"
exec python3 "$NEWS_ROOT/daily_pipeline.py" hook-context
