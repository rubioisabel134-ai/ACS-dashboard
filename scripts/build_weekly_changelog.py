#!/usr/bin/env python3
"""Build dashboard-readable weekly ACS changelog artifacts."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
from typing import Any


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build ACS weekly changelog JSON and markdown")
    p.add_argument("--intel", required=True, type=pathlib.Path)
    p.add_argument("--proposals", required=True, type=pathlib.Path)
    p.add_argument("--latest-json", required=True, type=pathlib.Path)
    p.add_argument("--archive-json", required=True, type=pathlib.Path)
    p.add_argument("--latest-md", required=True, type=pathlib.Path)
    p.add_argument("--archive-md", required=True, type=pathlib.Path)
    return p.parse_args()


def read_json(path: pathlib.Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def summarize_errors(intel: dict[str, Any]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    examples: dict[str, str] = {}
    for drug in intel.get("drugs", []):
        for error in drug.get("errors") or []:
            counts[error] = counts.get(error, 0) + 1
            examples.setdefault(error, drug.get("name") or "Unknown")
    return [
        {"message": message, "count": count, "exampleDrug": examples.get(message)}
        for message, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def collect_trial_updates(intel: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for drug in intel.get("drugs", []):
        for trial in drug.get("clinicalTrials") or []:
            items.append(
                {
                    "drug": drug.get("name"),
                    "type": "trial",
                    "date": trial.get("lastUpdate") or trial.get("primaryCompletionDate") or trial.get("completionDate"),
                    "title": trial.get("title") or "ClinicalTrials.gov update",
                    "source": "ClinicalTrials.gov",
                    "link": trial.get("url") or "",
                    "nctId": trial.get("nctId") or "",
                    "status": trial.get("overallStatus") or "",
                    "primaryCompletionDate": trial.get("primaryCompletionDate"),
                    "completionDate": trial.get("completionDate"),
                }
            )
    return sorted(items, key=lambda item: item.get("date") or "", reverse=True)


def iso_year(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).year
    except ValueError:
        pass
    if len(value) >= 4 and value[:4].isdigit():
        return int(value[:4])
    return None


def source_rank(source: str) -> int:
    value = (source or "").lower()
    if "google" in value or "yahoo" in value or "people's pharmacy" in value:
        return 3
    if value.startswith("www.") or ".com" in value or ".org" in value or ".net" in value:
        return 0
    return 1


def press_update_score(item: dict[str, Any]) -> tuple[str, int, str]:
    date = item.get("date") or ""
    date_day = date[:10]
    return (date_day, -source_rank(item.get("source") or ""), date)


def collect_press_updates(intel: dict[str, Any]) -> list[dict[str, Any]]:
    run_year = iso_year(intel.get("generatedAtUTC")) or dt.date.today().year
    best_by_drug: dict[str, dict[str, Any]] = {}
    for drug in intel.get("drugs", []):
        for press in drug.get("companyPress") or []:
            date = press.get("publishedAt") or None
            if iso_year(date) != run_year:
                continue
            item = {
                "drug": drug.get("name"),
                "type": "press",
                "date": date,
                "title": press.get("title") or "Company press update",
                "source": press.get("source") or "Company press room",
                "link": press.get("link") or "",
            }
            key = item["drug"] or ""
            prior = best_by_drug.get(key)
            if prior is None or press_update_score(item) > press_update_score(prior):
                best_by_drug[key] = item
        for news in drug.get("googleNews") or []:
            date = news.get("publishedAt") or None
            if iso_year(date) != run_year:
                continue
            item = {
                "drug": drug.get("name"),
                "type": "news",
                "date": date,
                "title": news.get("title") or "News update",
                "source": news.get("source") or "Google News",
                "link": news.get("link") or "",
            }
            key = item["drug"] or ""
            prior = best_by_drug.get(key)
            if prior is None or press_update_score(item) > press_update_score(prior):
                best_by_drug[key] = item
    items = list(best_by_drug.values())
    return sorted(items, key=press_update_score, reverse=True)


def collect_card_changes(proposals: dict[str, Any]) -> list[dict[str, Any]]:
    changes = []
    for proposal in proposals.get("proposals") or []:
        field_changes = []
        for field, values in (proposal.get("changes") or {}).items():
            field_changes.append(
                {
                    "field": field,
                    "before": values.get("before"),
                    "after": values.get("after"),
                }
            )
        changes.append({"drug": proposal.get("drug"), "fields": field_changes})
    return changes


def write_json(path: pathlib.Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")


def write_markdown(path: pathlib.Path, payload: dict[str, Any]) -> None:
    def fmt(value: Any) -> str:
        if value is None or value == "":
            return "n/a"
        if isinstance(value, list):
            return ", ".join(str(item) for item in value) or "n/a"
        return str(value)

    lines: list[str] = []
    lines.append(f"# ACS Weekly Changelog ({payload['runDate']})")
    lines.append("")
    summary = payload["summary"]
    lines.append(f"- Drugs scanned: {summary.get('drugsScanned', 0)}")
    lines.append(f"- Trial updates: {summary.get('trialUpdates', 0)}")
    lines.append(f"- Press/news updates: {summary.get('pressUpdates', 0)}")
    lines.append(f"- Drug cards changed: {summary.get('cardChanges', 0)}")
    lines.append(f"- Source error groups: {summary.get('errorGroups', 0)}")
    lines.append("")

    lines.append("## Drug Card Changes")
    lines.append("")
    if not payload["cardChanges"]:
        lines.append("- No drug card changes were applied.")
    for change in payload["cardChanges"]:
        lines.append(f"### {change.get('drug')}")
        for field in change.get("fields", []):
            before = fmt(field.get("before"))
            after = fmt(field.get("after"))
            lines.append(f"- `{field.get('field')}`: `{before}` -> `{after}`")
        lines.append("")

    lines.append("## Trial Updates")
    lines.append("")
    if not payload["trialUpdates"]:
        lines.append("- No trial updates found.")
    for trial in payload["trialUpdates"][:40]:
        nct = f" [{trial.get('nctId')}]" if trial.get("nctId") else ""
        lines.append(
            f"- {trial.get('date') or 'n/a'} | {trial.get('drug')}{nct} | "
            f"{trial.get('status') or 'Unknown'} | {trial.get('title')} | {trial.get('link')}"
        )
    lines.append("")

    lines.append("## Press And News")
    lines.append("")
    lines.append("Latest dated current-year press/news item per asset.")
    lines.append("")
    if not payload["pressUpdates"]:
        lines.append("- No press/news updates found.")
    for press in payload["pressUpdates"][:40]:
        lines.append(
            f"- {press.get('date') or 'n/a'} | {press.get('drug')} | "
            f"{press.get('source')} | [{press.get('title')}]({press.get('link')})"
        )
    lines.append("")

    lines.append("## Source Errors")
    lines.append("")
    if not payload["sourceErrors"]:
        lines.append("- No source errors recorded.")
    for error in payload["sourceErrors"]:
        lines.append(
            f"- {error.get('count')} asset(s): {error.get('message')} "
            f"(example: {error.get('exampleDrug')})"
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    intel = read_json(args.intel)
    proposals = read_json(args.proposals)
    run_date = dt.date.today().isoformat()

    trial_updates = collect_trial_updates(intel)
    press_updates = collect_press_updates(intel)
    card_changes = collect_card_changes(proposals)
    source_errors = summarize_errors(intel)

    payload = {
        "generatedAtUTC": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "runDate": run_date,
        "summary": {
            "drugsScanned": (intel.get("summary") or {}).get("drugsScanned", len(intel.get("drugs", []))),
            "trialUpdates": len(trial_updates),
            "pressUpdates": len(press_updates),
            "cardChanges": len(card_changes),
            "errorGroups": len(source_errors),
        },
        "cardChanges": card_changes,
        "trialUpdates": trial_updates,
        "pressUpdates": press_updates,
        "sourceErrors": source_errors,
    }

    write_json(args.latest_json, payload)
    write_json(args.archive_json, payload)
    write_markdown(args.latest_md, payload)
    write_markdown(args.archive_md, payload)
    print(f"Wrote weekly changelog: {args.latest_json}")
    print(f"Archived weekly changelog: {args.archive_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
