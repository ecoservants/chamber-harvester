#!/usr/bin/env python3
"""ChamberData A-Z harvester with detail-page enrichment and cleaner validation."""

from __future__ import annotations
import argparse, csv, re, time
from dataclasses import dataclass, asdict
from typing import List, Set, Tuple
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from harvest_common import (
    PHONE_RE,
    ZIP_RE,
    maybe_blank_chamber_email,
    choose_best_website,
    clean_address,
    clean_text,
    host_of,
    maybe_extract_email,
    normalize_url,
    require_safe_url,
    safe_goto,
    row_key,
    should_keep_row,
)

DETAIL_HINT_RE = re.compile(r"memberdirectory|memberprofile|listing|business", re.I)


@dataclass
class Member:
    name: str = ""
    phone: str = ""
    email: str = ""
    website: str = ""
    address: str = ""
    profile_url: str = ""
    letter: str = ""
    source_url: str = ""


def clean(s: str) -> str:
    return clean_text(s)


def infer_dbid2(url: str) -> str:
    q = parse_qs(urlparse(url).query)
    return q.get("dbid2", [""])[0]


def guess_letter_urls(dbid2: str) -> List[str]:
    base = "https://www.chamberdata.net"
    return [f"{base}/{chr(c)}_memberdirectory.aspx?dbid2={dbid2}" for c in range(ord('A'), ord('Z') + 1)]


def collect_member_links(html: str, base_url: str) -> List[Tuple[str, str]]:
    soup = BeautifulSoup(html or "", "lxml")
    out: List[Tuple[str, str]] = []
    seen = set()
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        text = clean(a.get_text(" "))
        if not href:
            continue
        absu = normalize_url(base_url, href)
        if not absu:
            continue
        if not DETAIL_HINT_RE.search(absu):
            continue
        if "dbid2=" not in absu.lower():
            continue
        if len(text) < 2 or len(text) > 120:
            continue
        key = (absu.lower(), text.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append((text, absu))
    return out


def enrich_member(page, base_url: str, letter: str, source_url: str, name_hint: str, profile_url: str) -> Member:
    safe_goto(page, profile_url, wait_until="load")
    page.wait_for_timeout(500)
    soup = BeautifulSoup(page.content() or "", "lxml")
    text = clean(soup.get_text(" "))
    chamber_host = host_of(source_url)

    name = name_hint
    for sel in ["h1", "h2", "strong", ".business-name", ".member-name"]:
        el = soup.select_one(sel)
        if el:
            cand = clean(el.get_text(" "))
            if 2 <= len(cand) <= 120:
                name = cand
                break

    phone = ""
    m = PHONE_RE.search(text)
    if m:
        phone = clean(m.group(0))

    email = ""
    mailto = soup.select_one('a[href^="mailto:"]')
    if mailto:
        email = maybe_extract_email(mailto.get("href", ""))
    if not email:
        email = maybe_extract_email(text)
    email = maybe_blank_chamber_email(email, chamber_host, profile_url)

    website_candidates = []
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        txt = clean(a.get_text(" "))
        absu = normalize_url(profile_url, href)
        if not absu:
            continue
        website_candidates.append((absu, txt))
    website = choose_best_website(website_candidates, chamber_host=chamber_host, business_name=name)

    address = ""
    addr = soup.select_one("address")
    if addr:
        address = clean_address(addr.get_text(" "))
    if not address:
        parts = []
        for raw in soup.stripped_strings:
            ss = clean(raw)
            if ZIP_RE.search(ss) or any(x in ss.lower() for x in ["suite", "ste", "road", "rd", "street", "st", "ave", "avenue", "blvd", "drive", "dr"]):
                parts.append(ss)
            if len(parts) >= 3:
                break
        address = clean_address(" ".join(parts))

    return Member(name=name, phone=phone, email=email, website=website, address=address, profile_url=profile_url, letter=letter, source_url=source_url)


def write_csv(path: str, rows: List[Member]):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(Member()).keys()))
        w.writeheader()
        for r in rows:
            w.writerow(asdict(r))


def scrape(dbid2: str, out: str, headless: bool, delay: float, timeout_ms: int, max_profiles_per_letter: int):
    urls = guess_letter_urls(dbid2)
    seen: Set[str] = set()
    all_rows: List[Member] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(timeout_ms)
        for u in urls:
            seg = u.rstrip('/').split('/')[-1]
            letter = (seg[0].upper() if seg else 'A')
            safe_goto(page, u, wait_until="load")
            page.wait_for_timeout(700)
            links = collect_member_links(page.content(), u)[:max_profiles_per_letter]
            added = 0
            for name_hint, profile_url in links:
                try:
                    r = enrich_member(page, u, letter, u, name_hint, profile_url)
                except Exception:
                    continue
                if not should_keep_row(r.name, r.phone, r.address, r.profile_url, r.website, r.email):
                    continue
                k = row_key(r.name, r.phone, r.address, r.profile_url)
                if k in seen:
                    continue
                seen.add(k)
                all_rows.append(r)
                added += 1
            print(f"[{letter}] added {added}, total {len(all_rows)}")
            write_csv(out, all_rows)
            if delay:
                time.sleep(delay)
        browser.close()
    print(f"Saved {len(all_rows)} rows -> {out}")


def main():
    ap = argparse.ArgumentParser(description="ChamberData A-Z harvester (dbid2 required)")
    ap.add_argument("dbid2_or_url", help="Either dbid2 value (e.g. caram) or a chamberdata URL containing ?dbid2=caram")
    ap.add_argument("--out", default="chamberdata_members.csv")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--delay", type=float, default=0.6)
    ap.add_argument("--timeout-ms", type=int, default=60000)
    ap.add_argument("--max-profiles-per-letter", type=int, default=60)
    args = ap.parse_args()
    dbid2 = args.dbid2_or_url
    if "dbid2=" in dbid2:
        dbid2 = infer_dbid2(dbid2)
    if not dbid2:
        raise SystemExit("Could not infer dbid2. Provide like: caram")
    scrape(dbid2, args.out, args.headless, max(0.0, args.delay), max(5000, args.timeout_ms), max(1, args.max_profiles_per_letter))


if __name__ == "__main__":
    main()
