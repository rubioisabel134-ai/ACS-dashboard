#!/bin/bash
set -euo pipefail

ROOT="/Users/isabelschlaepfer/ACS-dashboard"
LOG_DIR="$ROOT/logs"
STAMP="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="$LOG_DIR/acs-ci-weekly-$STAMP.log"

mkdir -p "$LOG_DIR" "$ROOT/docs/automation"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "[$(date)] Starting ACS weekly automation"
cd "$ROOT"

STASHED=0
STASH_MARKER="acs-weekly-autostash-$STAMP"

restore_stash() {
  if [ "$STASHED" -eq 1 ]; then
    local ref
    ref="$(git stash list | awk -F: -v marker="$STASH_MARKER" '$0 ~ marker {print $1; exit}')"
    if [ -n "$ref" ]; then
      echo "[$(date)] Restoring local changes from $ref"
      git stash pop "$ref" || echo "[$(date)] Auto-restore had conflicts; resolve manually with: git stash list && git stash pop"
    fi
  fi
}

trap restore_stash EXIT

if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$(git ls-files --others --exclude-standard)" ]; then
  echo "[$(date)] Local changes detected; auto-stashing before pull"
  git stash push -u -m "$STASH_MARKER" >/dev/null
  STASHED=1
fi

echo "[$(date)] Pulling latest main"
git pull --rebase origin main

echo "[$(date)] Updating trials + weekly intel (7-day window)"
python3 scripts/acs_intel_update.py --days 7 --max-news 15 --max-trials 15

echo "[$(date)] Syncing intel into dashboard cards"
python3 scripts/sync_intel_to_dashboard.py \
  --intel reports/latest.json \
  --dashboard data/acs-drugs.json \
  --proposal-out reports/proposed_changes.json \
  --apply

CAPTURE_FILE="docs/automation/playwright-weekly-latest.json"
if command -v node >/dev/null 2>&1; then
  echo "[$(date)] Running Playwright capture"
  if ! node scripts/playwright_capture_links.mjs --input reports/latest.json --output "$CAPTURE_FILE" --limit 40; then
    echo "[$(date)] Playwright capture failed; continuing with intel-only report"
  fi
else
  echo "[$(date)] Node.js not found; skipping Playwright capture"
fi

echo "[$(date)] Building weekly CI report"
python3 scripts/build_ci_report.py \
  --intel reports/latest.json \
  --capture "$CAPTURE_FILE" \
  --output docs/automation/ci-weekly-latest.md

echo "[$(date)] Staging weekly artifacts"
git add data/acs-drugs.json reports/proposed_changes.json docs/automation/ci-weekly-latest.md docs/automation/playwright-weekly-latest.json || true

if git diff --cached --quiet; then
  echo "[$(date)] No tracked changes to commit"
  exit 0
fi

echo "[$(date)] Committing and pushing"
git commit -m "ACS weekly CI automation: $(date +%F)"
git push origin main

echo "[$(date)] Completed successfully"
