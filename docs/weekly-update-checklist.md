# Weekly ACS CI Checklist

## 1) Update date
- Set `snapshotDate` in `data/acs-drugs.json` to `YYYY-MM-DD`.

## 2) Refresh catalysts
- Review each record with non-null `nextCatalystDate`.
- If a readout happened, move it into `statusSummary` and set the next catalyst.

## 3) Source hygiene
- Keep only primary sources where possible:
  - `clinicaltrials.gov` trial records
  - Company IR/press releases
  - FDA/EMA pages or approved label sources
  - Major congress release pages

## 4) Signal scoring
- `positive`: endpoint met / favorable execution
- `mixed`: incomplete, uncertain, or partially positive
- `negative`: failed endpoint, paused, or stopped
- `monitor`: early/limited public data

## 5) Commit
```bash
git add .
git commit -m "Weekly ACS dashboard update: YYYY-MM-DD"
git push
```
