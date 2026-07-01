#!/bin/zsh
set -u

export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

REPO="$HOME/my_repos/news"
LOG_DIR="$HOME/Library/Logs"
LOCK_DIR="$REPO/.git/news-auto-sync.lock"

mkdir -p "$LOG_DIR"
cd "$REPO" || exit 1

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')" "$1"
}

git_safe() {
  git -c core.fsmonitor=false "$@"
}

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  log "Another news git sync is already running; skip."
  exit 0
fi

cleanup() {
  rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap cleanup EXIT

if git_safe diff --quiet && git_safe diff --cached --quiet && [ -z "$(git_safe ls-files --others --exclude-standard)" ]; then
  log "No changes to sync."
  exit 0
fi

git_safe add -A

if git_safe diff --cached --quiet; then
  log "No staged changes after git add."
  exit 0
fi

commit_message="Auto sync news $(date '+%Y-%m-%d %H:%M:%S %Z')"
git_safe commit -m "$commit_message" || exit 1

branch="$(git_safe branch --show-current)"
if [ -z "$branch" ]; then
  log "Cannot push because the repository is in detached HEAD."
  exit 1
fi

if git_safe rev-parse --abbrev-ref --symbolic-full-name '@{u}' >/dev/null 2>&1; then
  git_safe push
else
  git_safe push -u origin "$branch"
fi

log "Synced branch $branch."
