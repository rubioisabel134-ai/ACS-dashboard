#!/usr/bin/env python3
"""Sync intel output into dashboard card data.

Reads reports/latest.json and updates data/acs-drugs.json in-place.
Designed to be conservative and idempotent.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_INTEL = ROOT / "reports" / "latest.json"
DEFAULT_DASHBOARD = ROOT / "data" / "acs-drugs.json"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Sync ACS intel into dashboard data")
    p.add_argument("--intel", type=pathlib.Path, default=DEFAULT_INTEL)
    p.add_argument("--dashboard", type=pathlib.Path, default=DEFAULT_DASHBOARD)
    return p.parse_args()


def read_json(path: pathlib.Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def parse_date(s: str | None) -> dt.date | None:
    if not s:
        return None
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        return None


def best_trial(trials: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not trials:
        return None
    return sorted(trials, key=lambda t: t.get("lastUpdate") or "", reverse=True)[0]


def normalize_status(raw: str) -> str:
    return (raw or "Unknown").replace("_", " ").title()


def choose_catalyst_date(trial: dict[str, Any]) -> tuple[str | None, str]:
    today = dt.date.today()
    primary = parse_date(trial.get("primaryCompletionDate"))
    completion = parse_date(trial.get("completionDate"))
    nct = trial.get("nctId", "")

    if primary and primary >= today:
        return primary.isoformat(), f"Estimated primary completion ({nct})"
    if completion and completion >= today:
        return completion.isoformat(), f"Estimated completion ({nct})"
    return None, f"Monitor next registry update ({nct})"


def update_record_from_trial(record: dict[str, Any], trial: dict[str, Any]) -> bool:
    changed = False

    nct = trial.get("nctId", "")
    status = normalize_status(trial.get("overallStatus"))
    last_update = trial.get("lastUpdate") or "not disclosed"
    trial_url = trial.get("url")

    if nct and record.get("keyTrial") != nct and record.get("keyTrial") in {"Not disclosed", "", None}:
        record["keyTrial"] = nct
        changed = True

    auto_summary = f"ClinicalTrials.gov: {nct} status is {status} (last update {last_update})."
    current_summary = (record.get("statusSummary") or "").strip()
    can_overwrite = (
        not current_summary
        or current_summary.startswith("ClinicalTrials.gov:")
        or "watchlist placeholder" in current_summary.lower()
        or current_summary.lower().startswith("added as")
    )
    if can_overwrite and current_summary != auto_summary:
        record["statusSummary"] = auto_summary
        changed = True

    catalyst_date, catalyst_event = choose_catalyst_date(trial)
    if record.get("nextCatalystDate") != catalyst_date:
        record["nextCatalystDate"] = catalyst_date
        changed = True
    if record.get("nextCatalystEvent") != catalyst_event:
        record["nextCatalystEvent"] = catalyst_event
        changed = True

    links = record.get("sourceLinks") or []
    if trial_url and trial_url not in links:
        record["sourceLinks"] = [trial_url] + links[:2]
        changed = True

    return changed


def main() -> int:
    args = parse_args()
    intel = read_json(args.intel)
    dashboard = read_json(args.dashboard)

    by_name: dict[str, dict[str, Any]] = {
        (r.get("drug") or "").strip().lower(): r for r in dashboard.get("records", [])
    }

    updates = 0
    for d in intel.get("drugs", []):
        name = (d.get("name") or "").strip().lower()
        record = by_name.get(name)
        if not record:
            continue

        trial = best_trial(d.get("clinicalTrials") or [])
        if not trial:
            continue

        if update_record_from_trial(record, trial):
            updates += 1

    dashboard["snapshotDate"] = dt.date.today().isoformat()

    with args.dashboard.open("w", encoding="utf-8") as f:
        json.dump(dashboard, f, indent=2)
        f.write("\n")

    print(f"Updated records: {updates}")
    print(f"Wrote {args.dashboard}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
