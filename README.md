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
- `docs/weekly-update-checklist.md` - update process

## Run locally
Because this app fetches JSON, serve it from a local web server:

```bash
cd /Users/isabelschlaepfer/ACS-dashboard
python3 -m http.server 8080
# open http://localhost:8080
```

## Weekly update workflow
1. Open `data/acs-drugs.json`.
2. Set `snapshotDate` to today.
3. For each program, update:
   - `stage`
   - `statusSummary`
   - `nextCatalystDate`
   - `nextCatalystEvent`
   - `sourceLinks`
4. Commit and push to `main`.

## GitHub Pages
Recommended settings:
- Repository -> Settings -> Pages
- Source: `Deploy from a branch`
- Branch: `main` / root

Site URL will be:
`https://rubioisabel134-ai.github.io/ACS-dashboard/`
