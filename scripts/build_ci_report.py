#!/usr/bin/env python3
"""Build a concise daily CI markdown report from intel + optional Playwright capture."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
from typing import Any


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build daily ACS CI report")
    p.add_argument("--intel", required=True, type=pathlib.Path)
    p.add_argument("--capture", required=False, type=pathlib.Path)
    p.add_argument("--output", required=True, type=pathlib.Path)
    return p.parse_args()


def read_json(path: pathlib.Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_capture(path: pathlib.Path | None) -> dict[str, Any] | None:
    if not path or not path.exists():
        return None
    return read_json(path)


def main() -> int:
    args = parse_args()
    intel = read_json(args.intel)
    capture = load_capture(args.capture)

    lines: list[str] = []
    lines.append(f"# ACS Daily CI Report ({dt.date.today().isoformat()})")
    lines.append("")
    lines.append(f"- Generated (UTC): {intel.get('generatedAtUTC', 'n/a')}")
    lines.append(f"- Drugs scanned: {len(intel.get('drugs', []))}")
    lines.append(f"- News window: last {intel.get('days', 'n/a')} day(s)")
    if capture:
        lines.append(f"- Playwright links captured: {capture.get('totalLinks', 0)}")
    else:
        lines.append("- Playwright links captured: 0 (capture unavailable)")
    lines.append("")

    lines.append("## Trial Status Updates")
    lines.append("")
    trial_lines = 0
    for d in intel.get("drugs", []):
        trials = d.get("clinicalTrials", [])
        if not trials:
            continue
        for t in trials[:2]:
            nct = t.get("nctId", "")
            status = t.get("overallStatus", "Unknown")
            last = t.get("lastUpdate", "n/a")
            url = t.get("url") or ""
            lines.append(f"- {d.get('name')}: [{nct}] {status} | last update {last} | {url}")
            trial_lines += 1
    if trial_lines == 0:
        lines.append("- No matching trial status updates found in this run.")
    lines.append("")

    lines.append("## News Highlights")
    lines.append("")
    news_lines = 0
    for d in intel.get("drugs", []):
        news = d.get("googleNews", [])
        for n in news[:2]:
            pub = (n.get("publishedAt") or "n/a")[:10]
            source = n.get("source") or "Unknown source"
            title = n.get("title") or "Untitled"
            link = n.get("link") or ""
            lines.append(f"- {d.get('name')} | {pub} | {source} | [{title}]({link})")
            news_lines += 1
    if news_lines == 0:
        lines.append("- No matching news items found in this run.")
    lines.append("")

    lines.append("## Captured Link Validation")
    lines.append("")
    if not capture:
        lines.append("- Playwright capture file not available.")
    else:
        caps = capture.get("captures", [])
        if not caps:
            lines.append("- No links captured.")
        else:
            ok_count = sum(1 for c in caps if c.get("ok"))
            lines.append(f"- Successful captures: {ok_count}/{len(caps)}")
            for c in caps[:15]:
                status = "OK" if c.get("ok") else "FAIL"
                final_url = c.get("finalUrl") or c.get("link") or ""
                title = c.get("pageTitle") or c.get("title") or "Untitled"
                lines.append(f"- {status} | {c.get('drug')} | [{title}]({final_url})")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
