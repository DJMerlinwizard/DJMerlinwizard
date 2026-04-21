#!/usr/bin/env python3
"""Lead finder for U.S. real estate intent keywords across public sources.

Sources:
- Reddit (public search endpoint)
- Craigslist (RSS search across selected U.S. metro sites)
- Nextdoor (CSV export ingest; no public API)

Usage example:
    python lead_finder.py --sources reddit,craigslist \
      --keywords "refinance,first time home buyer,investment property" \
      --max-results 100 --output leads.jsonl
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from typing import Iterable, List, Optional

DEFAULT_KEYWORDS = [
    "refinance",
    "refi",
    "buy a home",
    "first time home buyer",
    "mortgage preapproval",
    "looking to buy house",
    "investment property",
    "rental property purchase",
    "duplex investment",
]

CRAIGSLIST_US_SITES = [
    "newyork.craigslist.org",
    "losangeles.craigslist.org",
    "chicago.craigslist.org",
    "dallas.craigslist.org",
    "miami.craigslist.org",
    "seattle.craigslist.org",
    "denver.craigslist.org",
    "phoenix.craigslist.org",
]

US_STATES = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado", "connecticut",
    "delaware", "florida", "georgia", "hawaii", "idaho", "illinois", "indiana", "iowa",
    "kansas", "kentucky", "louisiana", "maine", "maryland", "massachusetts", "michigan",
    "minnesota", "mississippi", "missouri", "montana", "nebraska", "nevada", "new hampshire",
    "new jersey", "new mexico", "new york", "north carolina", "north dakota", "ohio",
    "oklahoma", "oregon", "pennsylvania", "rhode island", "south carolina", "south dakota",
    "tennessee", "texas", "utah", "vermont", "virginia", "washington", "west virginia",
    "wisconsin", "wyoming", "district of columbia", "dc", "u.s.", "usa", "united states",
}

US_STATE_ABBR = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA",
    "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT",
    "VA", "WA", "WV", "WI", "WY", "DC",
}


@dataclass
class Lead:
    source: str
    title: str
    url: str
    created_utc: Optional[int]
    snippet: str
    matched_keywords: List[str]
    location_hint: str


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def extract_keywords(text: str, keywords: Iterable[str]) -> List[str]:
    normalized = normalize_text(text)
    matches = []
    for kw in keywords:
        pattern = r"\b" + re.escape(kw.lower()) + r"\b"
        if re.search(pattern, normalized):
            matches.append(kw)
    return matches


def looks_us_only(text: str) -> bool:
    normalized = normalize_text(text)
    if any(token in normalized for token in US_STATES):
        return True
    words = re.findall(r"\b[A-Z]{2}\b", text or "")
    if any(w in US_STATE_ABBR for w in words):
        return True
    # Heuristic: USD dollar references are often U.S.-centric in housing posts.
    if "$" in text and "cad" not in normalized and "aud" not in normalized:
        return True
    return False


def fetch_json(url: str, timeout: int = 20) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; USLeadFinder/1.0; +https://example.local)"
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_text(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; USLeadFinder/1.0; +https://example.local)"
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def reddit_search(keywords: List[str], max_results: int) -> List[Lead]:
    results: List[Lead] = []
    for kw in keywords:
        q = urllib.parse.quote_plus(kw)
        url = f"https://www.reddit.com/search.json?q={q}&sort=new&limit=50&t=week"
        try:
            payload = fetch_json(url)
        except Exception as exc:
            print(f"[warn] reddit query failed for '{kw}': {exc}")
            continue

        posts = payload.get("data", {}).get("children", [])
        for post in posts:
            data = post.get("data", {})
            title = data.get("title", "")
            body = data.get("selftext", "")
            full_text = f"{title} {body}"
            matched = extract_keywords(full_text, keywords)
            if not matched:
                continue
            if not looks_us_only(full_text + " " + data.get("subreddit_name_prefixed", "")):
                continue

            results.append(
                Lead(
                    source="reddit",
                    title=title,
                    url="https://www.reddit.com" + data.get("permalink", ""),
                    created_utc=int(data.get("created_utc", 0)) or None,
                    snippet=(body or "")[:220],
                    matched_keywords=matched,
                    location_hint=data.get("subreddit_name_prefixed", ""),
                )
            )
            if len(results) >= max_results:
                return dedupe(results)
        time.sleep(0.5)
    return dedupe(results)


def parse_rss_items(xml_text: str) -> List[dict]:
    root = ET.fromstring(xml_text)
    items = []
    for item in root.findall("./channel/item"):
        items.append(
            {
                "title": html.unescape(item.findtext("title", default="")),
                "link": item.findtext("link", default=""),
                "description": html.unescape(item.findtext("description", default="")),
                "pubDate": item.findtext("pubDate", default=""),
            }
        )
    return items


def craigslist_search(keywords: List[str], max_results: int) -> List[Lead]:
    results: List[Lead] = []
    for site in CRAIGSLIST_US_SITES:
        for kw in keywords:
            q = urllib.parse.quote_plus(kw)
            url = f"https://{site}/search/rea?query={q}&sort=date&format=rss"
            try:
                rss = fetch_text(url)
                items = parse_rss_items(rss)
            except Exception as exc:
                print(f"[warn] craigslist query failed for '{kw}' on {site}: {exc}")
                continue

            for item in items:
                text = f"{item['title']} {item['description']}"
                matched = extract_keywords(text, keywords)
                if not matched:
                    continue
                if not looks_us_only(text + " " + site):
                    continue

                created_utc = None
                if item["pubDate"]:
                    try:
                        created_utc = int(dt.datetime.strptime(
                            item["pubDate"], "%a, %d %b %Y %H:%M:%S %z"
                        ).timestamp())
                    except ValueError:
                        pass

                results.append(
                    Lead(
                        source="craigslist",
                        title=item["title"],
                        url=item["link"],
                        created_utc=created_utc,
                        snippet=item["description"][:220],
                        matched_keywords=matched,
                        location_hint=site,
                    )
                )
                if len(results) >= max_results:
                    return dedupe(results)
            time.sleep(0.2)
    return dedupe(results)


def nextdoor_csv_ingest(csv_path: str, keywords: List[str], max_results: int) -> List[Lead]:
    """Ingests manually exported/community-shared Nextdoor posts from CSV.

    Expected columns (flexible): title, body/content/text, url, created_utc, location.
    """
    results: List[Lead] = []
    with open(csv_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            title = row.get("title", "")
            body = row.get("body") or row.get("content") or row.get("text") or ""
            text = f"{title} {body}"
            matched = extract_keywords(text, keywords)
            if not matched:
                continue
            location = row.get("location", "")
            if not looks_us_only(text + " " + location):
                continue
            created = row.get("created_utc", "")
            created_utc = int(created) if created.isdigit() else None
            results.append(
                Lead(
                    source="nextdoor",
                    title=title or "(untitled)",
                    url=row.get("url", ""),
                    created_utc=created_utc,
                    snippet=body[:220],
                    matched_keywords=matched,
                    location_hint=location,
                )
            )
            if len(results) >= max_results:
                break
    return dedupe(results)


def dedupe(leads: List[Lead]) -> List[Lead]:
    seen = set()
    out = []
    for lead in leads:
        key = (lead.source, lead.url or lead.title)
        if key in seen:
            continue
        seen.add(key)
        out.append(lead)
    return out


def sort_by_recent(leads: List[Lead]) -> List[Lead]:
    return sorted(leads, key=lambda x: x.created_utc or 0, reverse=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Find U.S. mortgage/home-purchase intent leads.")
    parser.add_argument(
        "--sources",
        default="reddit,craigslist",
        help="Comma-separated list: reddit,craigslist,nextdoor",
    )
    parser.add_argument(
        "--keywords",
        default=",".join(DEFAULT_KEYWORDS),
        help="Comma-separated keywords to match.",
    )
    parser.add_argument("--max-results", type=int, default=100)
    parser.add_argument("--nextdoor-csv", help="Path to Nextdoor CSV export (required when using nextdoor source)")
    parser.add_argument("--output", default="", help="Write JSONL output to file path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    sources = [s.strip().lower() for s in args.sources.split(",") if s.strip()]
    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]

    all_leads: List[Lead] = []

    if "reddit" in sources:
        all_leads.extend(reddit_search(keywords, args.max_results))
    if "craigslist" in sources:
        all_leads.extend(craigslist_search(keywords, args.max_results))
    if "nextdoor" in sources:
        if not args.nextdoor_csv:
            raise SystemExit("--nextdoor-csv is required when using nextdoor source")
        all_leads.extend(nextdoor_csv_ingest(args.nextdoor_csv, keywords, args.max_results))

    all_leads = sort_by_recent(dedupe(all_leads))[: args.max_results]

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            for lead in all_leads:
                fh.write(json.dumps(asdict(lead), ensure_ascii=False) + "\n")
        print(f"Wrote {len(all_leads)} leads to {args.output}")
    else:
        for lead in all_leads:
            ts = dt.datetime.utcfromtimestamp(lead.created_utc).isoformat() if lead.created_utc else "n/a"
            print(f"[{lead.source}] {lead.title} | {ts} | {lead.url}")
            print(f"  keywords={','.join(lead.matched_keywords)} | loc={lead.location_hint}")


if __name__ == "__main__":
    main()
