# Weekly ACS Intel Runbook

## 1) Run the weekly automation

```bash
cd /Users/isabelschlaepfer/ACS-dashboard
/bin/bash scripts/ci_weekly_automation.sh
```

Default behavior is now `review-only`:
- the script updates files and stages them
- it does **not** commit or push unless you explicitly run `--push`
- it also refuses to auto-stash local edits unless you explicitly run `--autostash`

Use this only after review:

```bash
/bin/bash scripts/ci_weekly_automation.sh --push
```

Only use this when you know you want the script to stash local edits first:

```bash
/bin/bash scripts/ci_weekly_automation.sh --autostash
```

## 2) Review the weekly summary

Open:
- `docs/automation/ci-weekly-latest.md`

```bash
nano docs/automation/ci-weekly-latest.md
```

Check:
- new trial updates
- new company press hits
- new relevant news
- obvious false positives

## 3) Review proposed dashboard-card changes

Open:
- `data/proposed-changes.json`

```bash
nano data/proposed-changes.json
```

Check:
- stage changes
- catalyst date changes
- signal changes
- source link changes
- termination/discontinuation updates

## 4) Review the raw intel feed if needed

Open:
- `data/intel-latest.json`
- `data/intel-news-log.csv`

```bash
nano data/intel-news-log.csv
```

Use this when you want to inspect or remove suspicious feed items.

## 5) If something is wrong, edit the right file

### Wrong dashboard card update

Edit:
- `data/acs-drugs.json`

```bash
nano data/acs-drugs.json
```

Use this when the card content is wrong but the raw intel can stay.

### Wrong feed/news item

Edit:
- `data/intel-latest.json`
- `data/intel-news-log.csv`

Use this when the item itself should not appear in the dashboard feed.

### Repeated filtering problem

Edit:
- `scripts/acs_intel_update.py`

```bash
nano scripts/acs_intel_update.py
```

Then rerun:

```bash
/bin/bash scripts/ci_weekly_automation.sh
```

## 6) Check git status

```bash
git status
```

## 7) Commit and push if everything looks correct

```bash
git commit -m "Weekly ACS intel refresh: YYYY-MM-DD"
git push origin main
```

Alternative:

```bash
/bin/bash scripts/ci_weekly_automation.sh --push
```

## Quick rule

- Wrong card content: edit `data/acs-drugs.json`
- Wrong proposed change: inspect `data/proposed-changes.json`
- Wrong feed/news item: edit `data/intel-latest.json` or `data/intel-news-log.csv`
- Repeated false positive: fix `scripts/acs_intel_update.py`
