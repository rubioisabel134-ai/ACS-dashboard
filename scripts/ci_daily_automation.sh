#!/bin/bash
set -euo pipefail

ROOT="/Users/isabelschlaepfer/ACS-dashboard"
LOG_DIR="$ROOT/logs"
STAMP="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="$LOG_DIR/acs-ci-daily-$STAMP.log"

mkdir -p "$LOG_DIR" "$ROOT/docs/automation"

# Capture both stdout/stderr in a timestamped log.
exec > >(tee -a "$LOG_FILE") 2>&1

echo "[$(date)] Starting ACS daily automation"
cd "$ROOT"

echo "[$(date)] Pulling latest main"
git pull --rebase origin main

echo "[$(date)] Running ACS intel updater"
python3 scripts/acs_intel_update.py --days 1 --max-news 10 --max-trials 10

CAPTURE_FILE="docs/automation/playwright-latest.json"
if command -v node >/dev/null 2>&1; then
  echo "[$(date)] Running Playwright capture"
  if ! node scripts/playwright_capture_links.mjs --input reports/latest.json --output "$CAPTURE_FILE" --limit 25; then
    echo "[$(date)] Playwright capture failed; continuing with intel-only report"
  fi
else
  echo "[$(date)] Node.js not found; skipping Playwright capture"
fi

echo "[$(date)] Building daily CI report"
python3 scripts/build_ci_report.py \
  --intel reports/latest.json \
  --capture "$CAPTURE_FILE" \
  --output docs/automation/ci-daily-latest.md

echo "[$(date)] Staging generated daily artifacts"
git add docs/automation/ci-daily-latest.md docs/automation/playwright-latest.json || true

if git diff --cached --quiet; then
  echo "[$(date)] No tracked changes to commit"
  exit 0
fi

echo "[$(date)] Committing and pushing"
git commit -m "ACS daily CI automation: $(date +%F)"
git push origin main

echo "[$(date)] Completed successfully"
