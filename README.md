# ACS Dashboard (GitHub Pages)

Static competitive-intelligence dashboard for acute coronary syndromes (ACS), including:
- Acute treatment agents
- Chronic post-ACS prevention assets
- Pipeline programs with trial catalysts

## Files
- `index.html` - dashboard shell
- `styles.css` - visual design
- `app.js` - filtering, card rendering, charts, table
- `data/acs-drugs.json` - weekly-updated source of truth
- `config/tracked_drugs.json` - tracked ACS drugs and keyword aliases for automation
- `scripts/acs_intel_update.py` - on-demand updater (ClinicalTrials.gov + Google News RSS)
- `reports/latest.md` - latest generated intelligence report
- `reports/latest.json` - latest generated machine-readable report
- `docs/weekly-update-checklist.md` - update process

## Run locally
Because this app fetches JSON, serve it from a local web server:

```bash
cd /Users/isabelschlaepfer/ACS-dashboard
python3 -m http.server 8080
# open http://localhost:8080
```

## Weekly update workflow
1. Run the updater:
```bash
cd /Users/isabelschlaepfer/ACS-dashboard
python3 scripts/acs_intel_update.py --days 7
```
2. Review `reports/latest.md` and validate key items against primary sources.
3. Update `data/acs-drugs.json`:
   - `snapshotDate`
   - `stage`
   - `statusSummary`
   - `nextCatalystDate`
   - `nextCatalystEvent`
   - `sourceLinks`
4. Commit and push to `main`.

### Updater options
```bash
# single drug on demand
python3 scripts/acs_intel_update.py --drug Zalunfiban --days 3

# only ClinicalTrials.gov checks
python3 scripts/acs_intel_update.py --trials-only

# only Google News checks
python3 scripts/acs_intel_update.py --news-only --days 1
```

Edit tracked assets and aliases in `config/tracked_drugs.json` (example included for `Xolatryp` / `Nyrada`).

If a source is temporarily unreachable, the script still finishes and records the error under each drug in `reports/latest.json`.

## Daily autonomous run (8:00 AM MST / Phoenix)

Automation scripts:
- `scripts/ci_daily_automation.sh` (orchestrator)
- `scripts/ci_weekly_automation.sh` (weekly orchestrator with dashboard card sync)
- `scripts/playwright_capture_links.mjs` (headless Playwright link capture)
- `scripts/build_ci_report.py` (builds `docs/automation/ci-daily-latest.md`)
- `scripts/sync_intel_to_dashboard.py` (updates `data/acs-drugs.json` from latest trial intel)

Install Playwright once (optional but recommended):
```bash
cd /Users/isabelschlaepfer/ACS-dashboard
npm init -y
npm i -D playwright
npx playwright install chromium
```

Run once manually:
```bash
cd /Users/isabelschlaepfer/ACS-dashboard
/bin/bash scripts/ci_daily_automation.sh
```

Run weekly manually (updates cards + weekly report + commits if changed):
```bash
cd /Users/isabelschlaepfer/ACS-dashboard
/bin/bash scripts/ci_weekly_automation.sh
```

Install cron (local machine):
```bash
crontab -l > /tmp/mycron
echo 'CRON_TZ=America/Phoenix' >> /tmp/mycron
echo '0 8 * * * cd /Users/isabelschlaepfer/ACS-dashboard && /bin/bash scripts/ci_daily_automation.sh' >> /tmp/mycron
crontab /tmp/mycron
rm /tmp/mycron
crontab -l
```

## GitHub Pages
Recommended settings:
- Repository -> Settings -> Pages
- Source: `GitHub Actions`

Site URL will be:
`https://rubioisabel134-ai.github.io/ACS-dashboard/`
