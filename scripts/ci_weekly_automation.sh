#!/bin/bash
set -euo pipefail

PUSH_CHANGES=0
AUTOSTASH=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --push)
      PUSH_CHANGES=1
      ;;
    --autostash)
      AUTOSTASH=1
      ;;
    *)
      echo "Usage: /bin/bash scripts/ci_weekly_automation.sh [--push] [--autostash]"
      exit 1
      ;;
  esac
  shift
done

ROOT="/Users/isabelschlaepfer/ACS-dashboard"
LOG_DIR="$ROOT/logs"
STAMP="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="$LOG_DIR/acs-ci-weekly-$STAMP.log"
INTEL_FILE="$ROOT/data/intel-latest.json"
PROPOSAL_FILE="$ROOT/data/proposed-changes.json"

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
  if [ "$AUTOSTASH" -ne 1 ]; then
    echo "[$(date)] Local changes detected; refusing to auto-stash by default"
    echo "[$(date)] Commit, stash, or clean your worktree first."
    echo "[$(date)] If you explicitly want auto-stash, rerun with:"
    echo "  /bin/bash scripts/ci_weekly_automation.sh --autostash"
    exit 1
  fi
  echo "[$(date)] Local changes detected; auto-stashing before pull"
  git stash push -u -m "$STASH_MARKER" >/dev/null
  STASHED=1
fi

echo "[$(date)] Pulling latest main"
git pull --rebase origin main

echo "[$(date)] Updating trials + weekly intel (7-day window)"
python3 scripts/acs_intel_update.py \
  --days 7 \
  --max-news 15 \
  --max-trials 15 \
  --latest-json-path data/intel-latest.json \
  --latest-md-path docs/automation/intel-latest.md \
  --news-csv-path data/intel-news-log.csv

echo "[$(date)] Syncing intel into dashboard cards"
python3 scripts/sync_intel_to_dashboard.py \
  --intel data/intel-latest.json \
  --dashboard data/acs-drugs.json \
  --proposal-out data/proposed-changes.json \
  --apply

CAPTURE_FILE="docs/automation/playwright-weekly-latest.json"
if command -v node >/dev/null 2>&1; then
  echo "[$(date)] Running Playwright capture"
  if ! node scripts/playwright_capture_links.mjs --input data/intel-latest.json --output "$CAPTURE_FILE" --limit 40; then
    echo "[$(date)] Playwright capture failed; continuing with intel-only report"
  fi
else
  echo "[$(date)] Node.js not found; skipping Playwright capture"
fi

echo "[$(date)] Building weekly CI report"
python3 scripts/build_ci_report.py \
  --intel data/intel-latest.json \
  --capture "$CAPTURE_FILE" \
  --output docs/automation/ci-weekly-latest.md

echo "[$(date)] Weekly run summary"
python3 - <<'PY' "$INTEL_FILE" "$PROPOSAL_FILE" "$PUSH_CHANGES"
import json
import pathlib
import sys

intel_path = pathlib.Path(sys.argv[1])
proposal_path = pathlib.Path(sys.argv[2])
push_changes = sys.argv[3] == "1"

intel = json.loads(intel_path.read_text()) if intel_path.exists() else {}
proposal = json.loads(proposal_path.read_text()) if proposal_path.exists() else {}
summary = intel.get("summary") or {}

print(f"  - Drugs scanned: {summary.get('drugsScanned', 0)}")
print(f"  - Drugs with errors: {summary.get('drugsWithErrors', 0)}")
print(f"  - Trial hits: {summary.get('trialHits', 0)}")
print(f"  - Company press hits: {summary.get('companyPressHits', 0)}")
print(f"  - Google News hits: {summary.get('googleNewsHits', 0)}")
print(f"  - Proposed dashboard updates: {proposal.get('updates', 0)}")
print(f"  - Push mode: {'enabled' if push_changes else 'disabled (review-only)'}")
PY

echo "[$(date)] Staging weekly artifacts"
git add data/acs-drugs.json data/intel-latest.json data/intel-news-log.csv data/proposed-changes.json docs/automation/intel-latest.md docs/automation/ci-weekly-latest.md docs/automation/playwright-weekly-latest.json || true

if git diff --cached --quiet; then
  echo "[$(date)] No tracked changes to commit"
  exit 0
fi

if [ "$PUSH_CHANGES" -ne 1 ]; then
  echo "[$(date)] Review-only mode: leaving changes staged locally"
  echo "[$(date)] Review docs/automation/ci-weekly-latest.md and data/proposed-changes.json"
  echo "[$(date)] If everything looks correct, run:"
  echo "  git commit -m \"ACS weekly CI automation: $(date +%F)\""
  echo "  git push origin main"
  exit 0
fi

echo "[$(date)] Committing and pushing"
git commit -m "ACS weekly CI automation: $(date +%F)"
git push origin main

echo "[$(date)] Completed successfully"
