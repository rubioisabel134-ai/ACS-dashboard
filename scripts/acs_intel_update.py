#!/usr/bin/env python3
"""Fetch ACS drug updates from ClinicalTrials.gov, company press rooms, and discovery news.

Usage:
  python3 scripts/acs_intel_update.py --days 7
  python3 scripts/acs_intel_update.py --drug Zalunfiban --drug Obicetrapib
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import email.utils
import html
import json
import pathlib
import re
import subprocess
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
    parser.add_argument("--latest-json-path", type=pathlib.Path, default=ROOT / "data" / "intel-latest.json")
    parser.add_argument("--latest-md-path", type=pathlib.Path, default=ROOT / "docs" / "automation" / "intel-latest.md")
    parser.add_argument("--news-csv-path", type=pathlib.Path, default=ROOT / "data" / "intel-news-log.csv")
    parser.add_argument("--archive", action="store_true", help="Also write timestamped archive files")
    parser.add_argument("--days", type=int, default=7, help="Google News recency window")
    parser.add_argument(
        "--target-year",
        type=int,
        default=dt.date.today().year,
        help="Only include events from this year (defaults to current year)",
    )
    parser.add_argument("--max-news", type=int, default=7)
    parser.add_argument("--max-trials", type=int, default=7)
    parser.add_argument("--drug", action="append", default=[], help="Filter by drug name (repeatable)")
    parser.add_argument("--news-only", action="store_true")
    parser.add_argument("--trials-only", action="store_true")
    return parser.parse_args()


def load_config(path: pathlib.Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def http_get_text(url: str, timeout: int = 12) -> str:
    command = [
        "curl",
        "--fail",
        "--location",
        "--silent",
        "--show-error",
        "--max-time",
        str(timeout),
        "--user-agent",
        "acs-dashboard-updater/1.0",
        url,
    ]
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            timeout=timeout + 3,
            text=True,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(f"request timed out after {timeout}s: {url}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip().splitlines()
        message = detail[-1] if detail else f"curl exit {exc.returncode}"
        raise RuntimeError(f"HTTP fetch failed ({message}): {url}") from exc
    return result.stdout


def http_get_json(url: str, timeout: int = 12) -> dict[str, Any]:
    return json.loads(http_get_text(url, timeout=timeout))


def parse_feed_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return parsed.date().isoformat()


def extract_year(value: str | None) -> int | None:
    if not value:
        return None
    m = re.search(r"(\d{4})", value)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def text_is_informative(title: str) -> bool:
    t = " ".join((title or "").split()).strip()
    if len(t) < 12:
        return False
    lowered = t.lower()
    blocked = {
        "read more",
        "learn more",
        "view all",
        "news",
        "press releases",
        "media",
        "home",
        "news & events",
        "news and events",
        "stock information",
        "analyst coverage",
        "corporate governance",
        "events & presentations",
        "events and presentations",
        "investor relations",
    }
    return lowered not in blocked


def item_is_relevant(
    title: str,
    link: str,
    alias_keywords: list[str],
    sponsor_terms: list[str],
    *,
    require_alias_match: bool = False,
) -> bool:
    hay = f"{title} {link}".lower().replace("-", " ")
    blocked_patterns = (
        r"\bst\s*patrick",
        r"\bparade\b",
        r"\banniversary\b",
        r"\bfestival\b",
        r"\bcharity\b",
        r"\bcommunity\b",
        r"\btestimonial\b",
        r"\bpatient story\b",
        r"\bspotlight\b",
        r"\bschool\b",
        r"\bfootball\b",
        r"\bweather\b",
        r"\btraffic\b",
        r"\bobituary\b",
    )
    if any(re.search(pattern, hay) for pattern in blocked_patterns):
        return False

    medical_context = re.search(
        r"\b(trial|study|phase|clinical|ct\.gov|nct\d{8}|results|topline|endpoint|enrollment|enrolment|"
        r"dosed|completion|complete|readout|cvot|mace|acs|ccs|cad|chd|ascvd|stemi|nstemi|"
        r"myocardial|coronary|post-mi|post myocardial infarction|secondary prevention|pci|"
        r"lipoprotein|lpa|ldl|press release|financial results|pipeline|license|licensing|agreement|"
        r"registration|commercialization|commercialisation|congress|acc|aha|esc|eas)\b",
        hay,
    )
    cv_context = re.search(
        r"\b(cvot|mace|acs|ccs|cad|chd|ascvd|stemi|nstemi|myocardial|coronary|heart attack|"
        r"atherothrombotic|atherosclerotic|secondary prevention|pci|cardiovascular|cardio|"
        r"lipoprotein|lpa|ldl|thrombo|thrombolytic|antiplatelet|anticoagulant|heart failure|mi)\b",
        hay,
    )
    financial_context = re.search(
        r"\b(financial results|business update|quarter results|full year|earnings)\b",
        hay,
    )
    alias_match = any(k in hay for k in alias_keywords if k)
    sponsor_match = any(t in hay for t in sponsor_terms if t)
    new_asset_match = re.search(
        r"\b(new drug|new candidate|pipeline|first patient dosed|phase [i1v]+|phase \d)\b",
        hay,
    )

    if require_alias_match and not alias_match:
        return False
    if alias_match and medical_context:
        return True
    if sponsor_match and cv_context and (medical_context or financial_context or new_asset_match):
        return True
    return bool(sponsor_match and new_asset_match and cv_context)


def company_press_item_is_relevant(
    title: str,
    link: str,
    description: str,
    alias_keywords: list[str],
    sponsor_terms: list[str],
) -> bool:
    title_link = f"{title} {link}".lower().replace("-", " ")
    alias_in_title_or_link = any(k in title_link for k in alias_keywords if k)
    if alias_in_title_or_link:
        return item_is_relevant(title, link, alias_keywords, sponsor_terms, require_alias_match=True)

    headline_is_off_topic = re.search(
        r"\b(obesity|weight|a1c|diabetes|glucose|triple agonist|retatrutide|tirzepatide|"
        r"alzheimer|oncology|cancer|immunology|dermatology)\b",
        title_link,
    )
    if headline_is_off_topic:
        return False

    return item_is_relevant(
        f"{title} {description}",
        link,
        alias_keywords,
        sponsor_terms,
        require_alias_match=True,
    )


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


def parse_press_feed(page: str, source_url: str) -> list[dict[str, str]]:
    stripped = page.lstrip()
    if not stripped.startswith("<?xml") and not stripped.startswith("<rss") and not stripped.startswith("<feed"):
        return []

    try:
        root = ET.fromstring(page)
    except ET.ParseError:
        return []

    items: list[dict[str, str]] = []
    if root.tag.endswith("rss") or root.find("./channel") is not None:
        for item in root.findall("./channel/item"):
            title = "".join(item.findtext("title") or "").strip()
            link = "".join(item.findtext("link") or "").strip()
            description = "".join(item.findtext("description") or "").strip()
            pub_date = "".join(item.findtext("pubDate") or "").strip()
            if title and link:
                items.append(
                    {
                        "title": html.unescape(title),
                        "link": urllib.parse.urljoin(source_url, link),
                        "description": html.unescape(re.sub(r"<[^>]+>", " ", description)),
                        "publishedAt": parse_feed_date(pub_date) or "",
                    }
                )
        return items

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entries = root.findall("./atom:entry", ns) or root.findall("./entry")
    for entry in entries:
        title = "".join(entry.findtext("atom:title", default="", namespaces=ns) or entry.findtext("title") or "").strip()
        link = ""
        for link_el in entry.findall("atom:link", ns) or entry.findall("link"):
            href = link_el.attrib.get("href", "").strip()
            if href:
                link = href
                break
        updated = (
            entry.findtext("atom:updated", default="", namespaces=ns)
            or entry.findtext("atom:published", default="", namespaces=ns)
            or entry.findtext("updated")
            or entry.findtext("published")
            or ""
        )
        summary = (
            entry.findtext("atom:summary", default="", namespaces=ns)
            or entry.findtext("atom:content", default="", namespaces=ns)
            or entry.findtext("summary")
            or entry.findtext("content")
            or ""
        )
        if title and link:
            items.append(
                {
                    "title": html.unescape(title),
                    "link": urllib.parse.urljoin(source_url, link),
                    "description": html.unescape(re.sub(r"<[^>]+>", " ", summary)),
                    "publishedAt": parse_feed_date(updated) or "",
                }
            )
    return items


def extract_page_title(page: str) -> str | None:
    candidates: list[str] = []
    for pattern in (r"<h1[^>]*>(.*?)</h1>", r"<title[^>]*>(.*?)</title>"):
        for match in re.finditer(pattern, page, flags=re.IGNORECASE | re.DOTALL):
            title = html.unescape(re.sub(r"<[^>]+>", " ", match.group(1)))
            title = re.sub(r"\s+", " ", title).strip()
            if title:
                candidates.append(title)
    for title in candidates:
        lowered = title.lower()
        if "backgrounder" in lowered or "complete the form" in lowered:
            continue
        if text_is_informative(title):
            return re.sub(r"\s+-\s+CeleCor Therapeutics$", "", title).strip()
    for title in candidates:
        title = re.sub(r"\s+", " ", title).strip()
        if text_is_informative(title):
            return title
    return None


def title_from_url_slug(url: str) -> str:
    path = urllib.parse.urlparse(url).path.strip("/")
    slug = path.rsplit("/", 1)[-1]
    title = re.sub(r"[-_]+", " ", slug)
    return re.sub(r"\s+", " ", title).strip()


def looks_like_article_url(url: str) -> bool:
    path = urllib.parse.urlparse(url).path.lower().strip("/")
    if not path:
        return False
    listing_markers = ("news", "media", "press-releases", "news-releases", "pipeline")
    if path in listing_markers or path.endswith(tuple(f"/{marker}" for marker in listing_markers)):
        return False
    return bool(re.search(r"(20\d{2}|news/[^/]+|press-release|news-release)", path))


def published_date_from_page(page: str) -> str | None:
    patterns = (
        r"Published on:\s*(?:<[^>]+>\s*)*([A-Z][a-z]+ \d{1,2}, \d{4})",
        r"\b([A-Z][a-z]+ \d{1,2}, \d{4})(?:\s+\d{1,2}:\d{2}\s*(?:am|pm)?\s*[A-Z]{2,4})?",
    )
    for pattern in patterns:
        match = re.search(pattern, page, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            continue
        try:
            return dt.datetime.strptime(html.unescape(match.group(1)).strip(), "%B %d, %Y").date().isoformat()
        except ValueError:
            continue
    return None


def extract_meta_description(page: str) -> str:
    patterns = (
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
    )
    for pattern in patterns:
        match = re.search(pattern, page, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return html.unescape(re.sub(r"\s+", " ", match.group(1))).strip()
    return ""


def company_press_search(
    drug: dict[str, Any],
    max_results: int,
    target_year: int,
) -> list[dict[str, Any]]:
    press_url = (drug.get("press_release_url") or "").strip()
    if not press_url:
        return []

    page = http_get_text(press_url)
    feed_items = parse_press_feed(page, press_url)
    parser = AnchorParser()
    if not feed_items:
        parser.feed(page)

    aliases = [a.lower() for a in (drug.get("aliases") or [drug.get("name", "")]) if a]
    sponsor_words = [w.lower() for w in (drug.get("sponsor", "").split()) if len(w) > 2]

    base_domain = urllib.parse.urlparse(press_url).netloc.lower()
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()

    page_title = extract_page_title(page)
    if page_title and text_is_informative(page_title):
        page_description = extract_meta_description(page)
        if company_press_item_is_relevant(page_title, press_url, page_description, aliases, sponsor_words):
            year = extract_year(page_title)
            if year is None or year == target_year:
                selected.append(
                    {
                        "title": re.sub(r"\s+", " ", page_title).strip(),
                        "link": press_url,
                        "source": base_domain or "company press room",
                        "publishedAt": published_date_from_page(page),
                    }
                )
                seen.add(press_url)
                if looks_like_article_url(press_url):
                    return selected[:max_results]

    if feed_items:
        for item in feed_items:
            absolute = item["link"]
            if absolute in seen:
                continue
            seen.add(absolute)
            title = re.sub(r"\s+", " ", item["title"]).strip()
            hay_title = f"{title} {item.get('description', '')}"
            if not text_is_informative(title):
                continue
            if not company_press_item_is_relevant(
                title,
                absolute,
                item.get("description", ""),
                aliases,
                sponsor_words,
            ):
                continue
            year = extract_year(item.get("publishedAt")) or extract_year(title) or extract_year(absolute)
            if year is not None and year != target_year:
                continue
            selected.append(
                {
                    "title": title,
                    "link": absolute,
                    "source": base_domain or "company press feed",
                    "publishedAt": item.get("publishedAt") or None,
                }
            )
            if len(selected) >= max_results:
                break
        return selected

    blocked_press_sections = (
        "stock-information",
        "analyst-coverage",
        "corporate-governance",
        "news-events",
        "newsroom",
        "investor-relations",
        "events-presentations",
        "sec-filings",
        "annual-meeting",
    )

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
        lowered_url = absolute.lower()
        if any(section in lowered_url for section in blocked_press_sections) and lowered_url.rstrip("/") == press_url.lower().rstrip("/"):
            continue

        text = html.unescape((link.get("text") or "").strip())
        candidate_text = text if text_is_informative(text) else title_from_url_slug(absolute)
        if not text_is_informative(candidate_text):
            continue
        if not company_press_item_is_relevant(candidate_text, absolute, "", aliases, sponsor_words):
            continue

        title = candidate_text
        published_at = None
        if not text_is_informative(text):
            try:
                article_page = http_get_text(absolute)
                title = extract_page_title(article_page) or candidate_text
                published_at = published_date_from_page(article_page)
            except Exception:
                title = candidate_text
                published_at = None

        year = extract_year(published_at) or extract_year(title) or extract_year(absolute)
        if year is not None and year != target_year:
            continue

        selected.append(
            {
                "title": re.sub(r"\s+", " ", title).strip(),
                "link": absolute,
                "source": base_domain or "company press room",
                "publishedAt": published_at,
            }
        )
        if len(selected) >= max_results:
            break

    return selected


def trial_summary_from_protocol(protocol: dict[str, Any]) -> dict[str, Any] | None:
    ident = protocol.get("identificationModule", {})
    status = protocol.get("statusModule", {})
    cond = protocol.get("conditionsModule", {})
    arms = protocol.get("armsInterventionsModule", {})
    nct_id = ident.get("nctId", "")
    if not nct_id:
        return None

    interventions = [
        i.get("name", "")
        for i in (arms.get("interventions") or [])
        if i.get("name")
    ]
    title = ident.get("briefTitle") or ident.get("officialTitle") or "Untitled"
    return {
        "nctId": nct_id,
        "title": title,
        "overallStatus": status.get("overallStatus", "Unknown"),
        "lastUpdate": (status.get("lastUpdatePostDateStruct") or {}).get("date"),
        "primaryCompletionDate": (status.get("primaryCompletionDateStruct") or {}).get("date"),
        "completionDate": (status.get("completionDateStruct") or {}).get("date"),
        "conditions": cond.get("conditions") or [],
        "interventions": interventions,
        "url": f"https://clinicaltrials.gov/study/{nct_id}",
    }


def clinicaltrials_search(
    drug: dict[str, Any],
    indication_terms: list[str],
    max_results: int,
    target_year: int,
) -> list[dict[str, Any]]:
    aliases = drug.get("trial_aliases") or drug.get("aliases") or [drug["name"]]
    drug_clause = " OR ".join(f'"{a}"' for a in aliases[:3])
    indication_clause = " OR ".join(f'"{i}"' for i in indication_terms[:6])
    term = f"({drug_clause}) AND ({indication_clause})"

    params = urllib.parse.urlencode({"query.term": term, "pageSize": str(max_results)})
    url = f"https://clinicaltrials.gov/api/v2/studies?{params}"
    search_payload = http_get_json(url)

    studies: list[dict[str, Any]] = []
    seen_nct_ids: set[str] = set()

    for nct_id in drug.get("nct_ids") or []:
        trial_payload = http_get_json(f"https://clinicaltrials.gov/api/v2/studies/{urllib.parse.quote(nct_id)}")
        trial = trial_summary_from_protocol(trial_payload.get("protocolSection", {}))
        if not trial:
            continue
        last_update = trial.get("lastUpdate")
        if extract_year(last_update) != target_year:
            continue
        studies.append(trial)
        seen_nct_ids.add(trial["nctId"])

    for s in search_payload.get("studies", []):
        protocol = s.get("protocolSection", {})
        trial = trial_summary_from_protocol(protocol)
        if not trial or trial["nctId"] in seen_nct_ids:
            continue

        title = trial.get("title") or "Untitled"
        interventions = trial.get("interventions") or []
        summary_text = " ".join([title, " ".join(interventions)]).lower()
        alias_hit = any(a.lower() in summary_text for a in aliases)

        if not alias_hit:
            continue

        last_update = trial.get("lastUpdate")
        if extract_year(last_update) != target_year:
            continue

        studies.append(trial)
        seen_nct_ids.add(trial["nctId"])

    studies.sort(key=lambda x: x.get("lastUpdate") or "", reverse=True)
    return studies[:max_results]


def google_news_search(
    drug: dict[str, Any],
    indication_terms: list[str],
    days: int,
    max_results: int,
    target_year: int,
) -> list[dict[str, Any]]:
    aliases = drug.get("aliases") or [drug["name"]]
    sponsor_words = [w.lower() for w in (drug.get("sponsor", "").split()) if len(w) > 2]
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

        if not text_is_informative(title):
            continue

        pub_iso = None
        if pub_date:
            try:
                pub_iso = email.utils.parsedate_to_datetime(pub_date).isoformat()
            except (TypeError, ValueError):
                pub_iso = None
        if extract_year(pub_iso) != target_year:
            continue
        if not item_is_relevant(title, link, aliases, sponsor_words):
            continue

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


def upsert_news_csv(report: dict[str, Any], csv_path: pathlib.Path) -> int:
    header = ["run_date", "event_date", "company", "drug", "event_type", "title", "source", "link", "nct_id", "status"]
    existing_rows: list[dict[str, str]] = []
    existing_keys: set[tuple[str, ...]] = set()

    if csv_path.exists():
        with csv_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing_rows.append(row)
                existing_keys.add(
                    (
                        row.get("drug", ""),
                        row.get("event_type", ""),
                        row.get("title", ""),
                        row.get("link", ""),
                        row.get("event_date", ""),
                    )
                )

    new_rows: list[dict[str, str]] = []
    run_date = report.get("generatedAtUTC", "")[:10]
    for d in report.get("drugs", []):
        company = d.get("sponsor", "")
        drug = d.get("name", "")

        for t in d.get("clinicalTrials", []):
            row = {
                "run_date": run_date,
                "event_date": t.get("lastUpdate") or "",
                "company": company,
                "drug": drug,
                "event_type": "trial",
                "title": t.get("title") or "",
                "source": "clinicaltrials.gov",
                "link": t.get("url") or "",
                "nct_id": t.get("nctId") or "",
                "status": t.get("overallStatus") or "",
            }
            key = (row["drug"], row["event_type"], row["title"], row["link"], row["event_date"])
            if key not in existing_keys:
                existing_keys.add(key)
                new_rows.append(row)

        for p in d.get("companyPress", []):
            row = {
                "run_date": run_date,
                "event_date": (p.get("publishedAt") or "")[:10],
                "company": company,
                "drug": drug,
                "event_type": "press",
                "title": p.get("title") or "",
                "source": p.get("source") or "company press room",
                "link": p.get("link") or "",
                "nct_id": "",
                "status": "",
            }
            key = (row["drug"], row["event_type"], row["title"], row["link"], row["event_date"])
            if key not in existing_keys:
                existing_keys.add(key)
                new_rows.append(row)

        for n in d.get("googleNews", []):
            row = {
                "run_date": run_date,
                "event_date": (n.get("publishedAt") or "")[:10],
                "company": company,
                "drug": drug,
                "event_type": "news",
                "title": n.get("title") or "",
                "source": n.get("source") or "Google News",
                "link": n.get("link") or "",
                "nct_id": "",
                "status": "",
            }
            key = (row["drug"], row["event_type"], row["title"], row["link"], row["event_date"])
            if key not in existing_keys:
                existing_keys.add(key)
                new_rows.append(row)

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows(existing_rows + new_rows)

    return len(new_rows)


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
            "discoveryWarnings": [],
            "errors": [],
        }

        if run_trials:
            try:
                entry["clinicalTrials"] = clinicaltrials_search(
                    drug,
                    indication_keywords,
                    args.max_trials,
                    args.target_year,
                )
            except Exception as exc:  # noqa: BLE001
                entry["errors"].append(f"clinicaltrials.gov: {exc}")

        if run_news:
            try:
                entry["companyPress"] = company_press_search(
                    drug,
                    args.max_news,
                    args.target_year,
                )
            except Exception as exc:  # noqa: BLE001
                entry["errors"].append(f"company press: {exc}")
            try:
                entry["googleNews"] = google_news_search(
                    drug,
                    indication_keywords,
                    args.days,
                    args.max_news,
                    args.target_year,
                )
            except Exception as exc:  # noqa: BLE001
                entry["discoveryWarnings"].append(f"google news: {exc}")

        report["drugs"].append(entry)

    drugs_with_errors = sum(1 for drug in report["drugs"] if drug.get("errors"))
    report["summary"] = {
        "drugsScanned": len(report["drugs"]),
        "drugsWithErrors": drugs_with_errors,
        "drugsWithDiscoveryWarnings": sum(1 for drug in report["drugs"] if drug.get("discoveryWarnings")),
        "trialHits": sum(len(drug.get("clinicalTrials") or []) for drug in report["drugs"]),
        "companyPressHits": sum(len(drug.get("companyPress") or []) for drug in report["drugs"]),
        "googleNewsHits": sum(len(drug.get("googleNews") or []) for drug in report["drugs"]),
    }

    args.latest_json_path.parent.mkdir(parents=True, exist_ok=True)
    args.latest_md_path.parent.mkdir(parents=True, exist_ok=True)

    with args.latest_json_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        f.write("\n")

    markdown = generate_markdown(report)
    args.latest_md_path.write_text(markdown, encoding="utf-8")

    if args.archive:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        json_path = args.output_dir / f"acs-intel-{stamp}.json"
        md_path = args.output_dir / f"acs-intel-{stamp}.md"
        with json_path.open("w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
            f.write("\n")
        md_path.write_text(markdown, encoding="utf-8")
        print(f"Wrote archive: {json_path}")
        print(f"Wrote archive: {md_path}")

    inserted = upsert_news_csv(report, args.news_csv_path)
    print(f"Updated latest json: {args.latest_json_path}")
    print(f"Updated latest markdown: {args.latest_md_path}")
    print(f"Updated csv log: {args.news_csv_path} (new rows: {inserted})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
