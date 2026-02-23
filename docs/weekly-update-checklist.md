# Weekly ACS CI Checklist

## 1) Run automated scan
```bash
cd /Users/isabelschlaepfer/ACS-dashboard
python3 scripts/acs_intel_update.py --days 7
```
- Review `reports/latest.md`.
- If needed, tune aliases in `config/tracked_drugs.json` and rerun.

## 2) Update date
- Set `snapshotDate` in `data/acs-drugs.json` to `YYYY-MM-DD`.

## 3) Refresh catalysts
- Review each record with non-null `nextCatalystDate`.
- If a readout happened, move it into `statusSummary` and set the next catalyst.

## 4) Source hygiene
- Keep only primary sources where possible:
  - `clinicaltrials.gov` trial records
  - Company IR/press releases
  - FDA/EMA pages or approved label sources
  - Major congress release pages

## 5) Signal scoring
- `positive`: endpoint met / favorable execution
- `mixed`: incomplete, uncertain, or partially positive
- `negative`: failed endpoint, paused, or stopped
- `monitor`: early/limited public data

## 6) Commit
```bash
git add .
git commit -m "Weekly ACS dashboard update: YYYY-MM-DD"
git push
```
