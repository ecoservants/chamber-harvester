#!/usr/bin/env python3
"""Atlas / GrowthZone-style directory harvester.

Targets URLs like:
  https://web.carlsbad.org/atlas/directory/search
  https://web.carlsbad.org/atlas/directory/all-categories
  https://web.carlsbad.org/atlas/directory/category/advertising

Strategy:
  1) If an /all-categories page exists, collect all category URLs
  2) Visit each category page and extract member cards + profile links
  3) Optionally open profile pages to enrich (email, contact, socials)

Designed to be driven by run_harvest.py.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import time
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

from harvest_common import choose_best_website, clean_address, host_of, maybe_blank_chamber_email, maybe_extract_email, normalize_url, row_key, should_keep_row, require_safe_url, safe_goto, log_info, log_error, log_summary, log_page_visit, log_row_extracted


CATEGORY_RE = re.compile(r"/atlas/directory/category/", re.I)
PROFILE_HINT_RE = re.compile(r"/atlas/directory/(?:member|profile|listing|business)/", re.I)
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)


@dataclass
class Row:
    name: str = ""
    phone: str = ""
    email: str = ""
    website: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    postal: str = ""
    category: str = ""
    profile_url: str = ""
    source_url: str = ""


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def safe_get_text(el) -> str:
    try:
        return norm(el.inner_text())
    except Exception:
        return ""


def extract_contact_from_profile(page, chamber_host: str, business_name: str = "") -> Tuple[str, str]:
    """Return (email, website) best-effort."""
    email = ""
    website = ""

    try:
        mailtos = page.locator('a[href^="mailto:"]').all()
        for a in mailtos:
            href = a.get_attribute("href") or ""
            cand = maybe_extract_email(href)
            if cand:
                email = cand
                break
    except Exception:
        pass

    if not email:
        try:
            txt = page.content()
            email = maybe_extract_email(txt)
        except Exception:
            pass

    candidates = []
    try:
        links = page.locator('a[href]').all()
        for a in links:
            href = a.get_attribute("href") or ""
            txt = safe_get_text(a)
            absu = normalize_url(page.url, href)
            if absu:
                candidates.append((absu, txt))
    except Exception:
        pass
    website = choose_best_website(candidates, chamber_host=chamber_host, business_name=business_name)

    return maybe_blank_chamber_email(email, chamber_host, page.url), website


def collect_category_urls(page, base: str) -> List[str]:
    """Collect /atlas/directory/category/* URLs on the page."""
    urls: Set[str] = set()
    anchors = page.locator("a[href]").all()
    for a in anchors:
        href = a.get_attribute("href") or ""
        if not href:
            continue
        absu = urljoin(base, href)
        if CATEGORY_RE.search(urlparse(absu).path):
            urls.add(absu.split("#")[0])
    return sorted(urls)


def guess_all_categories_url(start_url: str) -> str:
    p = urlparse(start_url)
    if "/atlas/directory/" not in p.path:
        return start_url
    base = start_url
    # normalize to /atlas/directory/all-categories
    prefix = p.path.split("/atlas/directory/")[0] + "/atlas/directory/all-categories"
    return p._replace(path=prefix, query="", fragment="").geturl()


def scrape_category_page(page, base: str, category_url: str, category_name: str, delay: float) -> List[Row]:
    safe_goto(page, category_url, wait_until="domcontentloaded")
    time.sleep(delay)

    rows: List[Row] = []

    # Prefer Learn More buttons
    learn_more = page.locator("a", has_text=re.compile(r"learn more", re.I)).all()
    profile_urls: Set[str] = set()
    for a in learn_more:
        href = a.get_attribute("href") or ""
        if href:
            profile_urls.add(urljoin(base, href))

    if not profile_urls:
        # fallback: any anchor that looks like a profile
        anchors = page.locator("a[href]").all()
        for a in anchors:
            href = a.get_attribute("href") or ""
            if not href:
                continue
            absu = urljoin(base, href)
            if PROFILE_HINT_RE.search(urlparse(absu).path):
                profile_urls.add(absu)

    # On category pages, some info is visible without opening profiles.
    # We'll try to derive card containers by walking up from Learn More anchors.
    for pu in sorted(profile_urls):
        r = Row(category=category_name, profile_url=pu, source_url=category_url)
        rows.append(r)

    return rows


def enrich_rows(page, base: str, rows: List[Row], delay: float, timeout_ms: int) -> None:
    for i, r in enumerate(rows, 1):
        if not r.profile_url:
            continue
        try:
            safe_goto(page, r.profile_url, wait_until="domcontentloaded", timeout=timeout_ms)
            time.sleep(delay)

            # Name often in h1
            try:
                h1 = page.locator("h1").first
                if h1:
                    r.name = r.name or safe_get_text(h1)
            except Exception:
                pass

            # Phone: common patterns
            try:
                tel = page.locator('a[href^="tel:"]').first
                href = tel.get_attribute("href") if tel else ""
                if href and href.lower().startswith("tel:"):
                    r.phone = r.phone or href.split(":", 1)[1].strip()
            except Exception:
                pass

            # Address block: best effort from visible text
            if not r.address:
                try:
                    addr = page.locator("address").first
                    txt = safe_get_text(addr)
                    r.address = clean_address(txt)
                except Exception:
                    pass

            email, website = extract_contact_from_profile(page, host_of(base), r.name)
            if email and not r.email:
                r.email = email
            if website and not r.website:
                r.website = website

        except PWTimeoutError:
            continue
        except Exception:
            continue


def write_csv(path: str, rows: List[Row]) -> None:
    fieldnames = list(asdict(Row()).keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(asdict(r))


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url", help="Atlas directory URL (search, all-categories, or category/*)")
    ap.add_argument("--out", default="atlas_members.csv")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--delay", type=float, default=0.6)
    ap.add_argument("--timeout-ms", type=int, default=60000)
    ap.add_argument("--max-categories", type=int, default=500)
    ap.add_argument("--enrich", action="store_true", help="Open each profile page to pull email/website/etc")
    args = ap.parse_args(argv)

    start_url = args.url
    base = f"{urlparse(start_url).scheme}://{urlparse(start_url).netloc}/"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        page = browser.new_page()

        # Prefer all-categories
        cat_url = guess_all_categories_url(start_url)
        category_urls: List[str] = []
        try:
            safe_goto(page, cat_url, wait_until="domcontentloaded", timeout=args.timeout_ms)
            time.sleep(args.delay)
            category_urls = collect_category_urls(page, base)
        except Exception:
            category_urls = []

        if not category_urls:
            # If the provided URL is already a category, just use it
            if CATEGORY_RE.search(urlparse(start_url).path):
                category_urls = [start_url]
            else:
                # fallback: use the start url as a single bucket
                category_urls = [start_url]

        category_urls = category_urls[: args.max_categories]

        all_rows: List[Row] = []
        seen_profiles: Set[str] = set()

        for cu in category_urls:
            category_name = urlparse(cu).path.rstrip("/").split("/")[-1]
            rows = scrape_category_page(page, base, cu, category_name, args.delay)
            for r in rows:
                if not should_keep_row(r.name or r.profile_url.split("/")[-1], r.phone, r.address, r.profile_url, r.website, r.email):
                    continue
                k = row_key(r.name or r.profile_url.split("/")[-1], r.phone, r.address, r.profile_url)
                if k in seen_profiles:
                    continue
                seen_profiles.add(k)
                all_rows.append(r)

        if args.enrich:
            enrich_rows(page, base, all_rows, args.delay, args.timeout_ms)

        browser.close()

    write_csv(args.out, all_rows)
    log_summary({"rows_saved": len(all_rows), "output_file": args.out})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
