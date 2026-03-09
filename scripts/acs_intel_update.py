#!/usr/bin/env python3
"""Fetch ACS drug updates from ClinicalTrials.gov and Google News RSS.

Usage:
  python3 scripts/acs_intel_update.py --days 7
  python3 scripts/acs_intel_update.py --drug Zalunfiban --drug Obicetrapib
"""

from __future__ import annotations

import argparse
import datetime as dt
import email.utils
import html
import json
import pathlib
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "tracked_drugs.json"
DEFAULT_OUTPUT_DIR = ROOT / "reports"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ACS intelligence updater")
    parser.add_argument("--config", type=pathlib.Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=pathlib.Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--days", type=int, default=7, help="Google News recency window")
    parser.add_argument("--max-news", type=int, default=7)
    parser.add_argument("--max-trials", type=int, default=7)
    parser.add_argument("--drug", action="append", default=[], help="Filter by drug name (repeatable)")
    parser.add_argument("--news-only", action="store_true")
    parser.add_argument("--trials-only", action="store_true")
    return parser.parse_args()


def load_config(path: pathlib.Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def http_get_json(url: str, timeout: int = 25) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "acs-dashboard-updater/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_get_text(url: str, timeout: int = 25) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "acs-dashboard-updater/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


class AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict[str, str]] = []
        self._current_href: str | None = None
        self._text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attr_map = {k.lower(): (v or "") for k, v in attrs}
        href = attr_map.get("href", "").strip()
        if not href:
            return
        self._current_href = href
        self._text_parts = []

    def handle_data(self, data: str) -> None:
        if self._current_href is not None:
            self._text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._current_href is None:
            return
        text = " ".join(" ".join(self._text_parts).split())
        self.links.append({"href": self._current_href, "text": text})
        self._current_href = None
        self._text_parts = []


def company_press_search(drug: dict[str, Any], max_results: int) -> list[dict[str, Any]]:
    press_url = (drug.get("press_release_url") or "").strip()
    if not press_url:
        return []

    page = http_get_text(press_url)
    parser = AnchorParser()
    parser.feed(page)

    aliases = [a.lower() for a in (drug.get("aliases") or [drug.get("name", "")]) if a]
    sponsor_words = [w.lower() for w in (drug.get("sponsor", "").split()) if len(w) > 2]
    keywords = aliases + sponsor_words

    base_domain = urllib.parse.urlparse(press_url).netloc.lower()
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()

    for link in parser.links:
        raw_href = link.get("href", "").strip()
        if not raw_href or raw_href.startswith("#") or raw_href.startswith("javascript:") or raw_href.startswith("mailto:"):
            continue
        absolute = urllib.parse.urljoin(press_url, raw_href)
        parsed = urllib.parse.urlparse(absolute)
        if parsed.scheme not in {"http", "https"}:
            continue
        if base_domain and base_domain not in parsed.netloc.lower():
            continue
        if absolute in seen:
            continue
        seen.add(absolute)

        text = html.unescape((link.get("text") or "").strip())
        hay = f"{text} {absolute}".lower()
        matched = any(k in hay for k in keywords if k)
        if not matched:
            continue

        title = text or parsed.path.rsplit("/", 1)[-1] or "Untitled"
        selected.append(
            {
                "title": re.sub(r"\s+", " ", title).strip(),
                "link": absolute,
                "source": base_domain or "company press room",
                "publishedAt": None,
            }
        )
        if len(selected) >= max_results:
            break

    return selected


def clinicaltrials_search(drug: dict[str, Any], indication_terms: list[str], max_results: int) -> list[dict[str, Any]]:
    aliases = drug.get("aliases") or [drug["name"]]
    drug_clause = " OR ".join(f'"{a}"' for a in aliases[:3])
    indication_clause = " OR ".join(f'"{i}"' for i in indication_terms[:6])
    term = f"({drug_clause}) AND ({indication_clause})"

    params = urllib.parse.urlencode({"query.term": term, "pageSize": str(max_results)})
    url = f"https://clinicaltrials.gov/api/v2/studies?{params}"
    payload = http_get_json(url)

    studies: list[dict[str, Any]] = []
    for s in payload.get("studies", []):
        protocol = s.get("protocolSection", {})
        ident = protocol.get("identificationModule", {})
        status = protocol.get("statusModule", {})
        cond = protocol.get("conditionsModule", {})
        arms = protocol.get("armsInterventionsModule", {})

        interventions = [
            i.get("name", "")
            for i in (arms.get("interventions") or [])
            if i.get("name")
        ]
        title = ident.get("briefTitle") or ident.get("officialTitle") or "Untitled"
        summary_text = " ".join([title, " ".join(interventions)]).lower()
        alias_hit = any(a.lower() in summary_text for a in aliases)

        if not alias_hit:
            continue

        studies.append(
            {
                "nctId": ident.get("nctId", ""),
                "title": title,
                "overallStatus": status.get("overallStatus", "Unknown"),
                "lastUpdate": (status.get("lastUpdatePostDateStruct") or {}).get("date"),
                "primaryCompletionDate": (status.get("primaryCompletionDateStruct") or {}).get("date"),
                "completionDate": (status.get("completionDateStruct") or {}).get("date"),
                "conditions": cond.get("conditions") or [],
                "interventions": interventions,
                "url": f"https://clinicaltrials.gov/study/{ident.get('nctId', '')}" if ident.get("nctId") else None,
            }
        )

    studies.sort(key=lambda x: x.get("lastUpdate") or "", reverse=True)
    return studies[:max_results]


def google_news_search(drug: dict[str, Any], indication_terms: list[str], days: int, max_results: int) -> list[dict[str, Any]]:
    aliases = drug.get("aliases") or [drug["name"]]
    drug_terms = " OR ".join(f'"{a}"' for a in aliases[:3])
    indication_terms_q = " OR ".join(f'"{k}"' for k in indication_terms[:4])
    query = f"({drug_terms}) ({indication_terms_q}) when:{days}d"

    params = urllib.parse.urlencode(
        {
            "q": query,
            "hl": "en-US",
            "gl": "US",
            "ceid": "US:en",
        }
    )
    url = f"https://news.google.com/rss/search?{params}"
    xml_text = http_get_text(url)

    root = ET.fromstring(xml_text)
    items = root.findall("./channel/item")

    entries: list[dict[str, Any]] = []
    seen = set()
    for item in items:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        source = item.find("source")
        source_name = (source.text or "").strip() if source is not None else ""

        key = (title.lower(), link)
        if key in seen:
            continue
        seen.add(key)

        pub_iso = None
        if pub_date:
            try:
                pub_iso = email.utils.parsedate_to_datetime(pub_date).isoformat()
            except (TypeError, ValueError):
                pub_iso = None

        entries.append(
            {
                "title": title,
                "source": source_name,
                "publishedAt": pub_iso,
                "link": link,
            }
        )

    entries.sort(key=lambda x: x.get("publishedAt") or "", reverse=True)
    return entries[:max_results]


def generate_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"# ACS Intel Update ({report['generatedAtUTC'][:10]})")
    lines.append("")
    lines.append(f"- Window: last {report['days']} day(s)")
    lines.append(f"- Drugs scanned: {len(report['drugs'])}")
    lines.append("")

    for drug in report["drugs"]:
        lines.append(f"## {drug['name']} ({drug['sponsor']})")
        lines.append("")

        trials = drug.get("clinicalTrials", [])
        press = drug.get("companyPress", [])
        news = drug.get("googleNews", [])

        lines.append(f"- ClinicalTrials.gov hits: {len(trials)}")
        lines.append(f"- Company press hits: {len(press)}")
        lines.append(f"- Google News hits: {len(news)}")
        lines.append("")

        if trials:
            lines.append("### Latest trial updates")
            for t in trials:
                title = t.get("title", "Untitled")
                status = t.get("overallStatus", "Unknown")
                last = t.get("lastUpdate", "n/a")
                nct = t.get("nctId", "")
                url = t.get("url") or ""
                lines.append(f"- [{nct}] {title} | Status: {status} | Last update: {last} | {url}")
            lines.append("")

        if press:
            lines.append("### Company press-room hits")
            for p in press:
                title = p.get("title", "Untitled")
                source = p.get("source", "Company press room")
                link = p.get("link", "")
                lines.append(f"- {source} | [{title}]({link})")
            lines.append("")

        if news:
            lines.append("### Latest Google News")
            for n in news:
                title = n.get("title", "Untitled")
                source = n.get("source", "Unknown source")
                pub = (n.get("publishedAt") or "n/a")[:10]
                link = n.get("link", "")
                lines.append(f"- {pub} | {source} | [{title}]({link})")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def filter_drugs(drugs: list[dict[str, Any]], names: list[str]) -> list[dict[str, Any]]:
    if not names:
        return drugs
    wanted = {n.lower().strip() for n in names}
    return [d for d in drugs if d.get("name", "").lower() in wanted]


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    indication_keywords = config.get("indication_keywords") or []
    drugs = filter_drugs(config.get("drugs") or [], args.drug)

    if not drugs:
        print("No matching drugs found in config. Check --drug names or config file.", file=sys.stderr)
        return 1

    run_trials = not args.news_only
    run_news = not args.trials_only

    report = {
        "generatedAtUTC": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "days": args.days,
        "drugs": [],
    }

    for drug in drugs:
        entry = {
            "name": drug.get("name"),
            "sponsor": drug.get("sponsor", "Unknown"),
            "aliases": drug.get("aliases") or [],
            "pressReleaseUrl": drug.get("press_release_url"),
            "clinicalTrials": [],
            "companyPress": [],
            "googleNews": [],
            "errors": [],
        }

        if run_trials:
            try:
                entry["clinicalTrials"] = clinicaltrials_search(drug, indication_keywords, args.max_trials)
            except Exception as exc:  # noqa: BLE001
                entry["errors"].append(f"clinicaltrials.gov: {exc}")

        if run_news:
            try:
                entry["companyPress"] = company_press_search(drug, args.max_news)
            except Exception as exc:  # noqa: BLE001
                entry["errors"].append(f"company press: {exc}")
            try:
                entry["googleNews"] = google_news_search(drug, indication_keywords, args.days, args.max_news)
            except Exception as exc:  # noqa: BLE001
                entry["errors"].append(f"google news: {exc}")

        report["drugs"].append(entry)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = args.output_dir / f"acs-intel-{stamp}.json"
    md_path = args.output_dir / f"acs-intel-{stamp}.md"
    latest_json = args.output_dir / "latest.json"
    latest_md = args.output_dir / "latest.md"

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    with latest_json.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    markdown = generate_markdown(report)
    md_path.write_text(markdown, encoding="utf-8")
    latest_md.write_text(markdown, encoding="utf-8")

    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    print(f"Updated {latest_json}")
    print(f"Updated {latest_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
