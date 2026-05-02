#!/usr/bin/env python3
"""
harvest_grid_directory.py — Grid/Tile-style Chamber directories (ChamberMaster/GrowthZone-like)

Supports:
- Grid/tile member listings where full info requires clicking profile pages
- Pagination (Next / numeric pages)
- Optional A–Z alpha pages (searchalpha) discovery and traversal

Example alpha directory:
  https://business.eastcountychamber.org/list/searchalpha/a

Install:
  pip install playwright beautifulsoup4 lxml
  python -m playwright install
"""

from __future__ import annotations

import argparse
import csv
import re
import string
import time
from dataclasses import dataclass, asdict
from typing import List, Set, Tuple, Optional, Iterable
from urllib.parse import urljoin, urldefrag, urlparse, urlencode, parse_qs, urlsplit, urlunsplit

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, Page, Frame

from harvest_common import normalize_url, require_safe_url, safe_goto, log_info, log_error, log_summary, log_page_visit, log_row_extracted

PHONE_RE = re.compile(r"(?:(?:\+?1\s*)?(?:\(\s*\d{3}\s*\)|\d{3})[-.\s]*)\d{3}[-.\s]*\d{4}")
BAD_LINK_RE = re.compile(r"^(javascript:|#)$", re.I)

PROFILE_HINTS = [
    "/list/member", "/member/", "/members/", "/directory/", "/listing/", "/biz/",
]

SEARCHALPHA_RE = re.compile(r"/list/searchalpha/([a-z])\b", re.I)

@dataclass
class Member:
    name: str = ""
    phone: str = ""
    email: str = ""
    website: str = ""
    address: str = ""
    profile_url: str = ""
    source_url: str = ""

def clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def norm_url(base: str, href: str) -> str:
    return normalize_url(base, href)

def looks_like_profile_href(href: str) -> bool:
    if not href:
        return False
    h = href.lower()
    if h.startswith(("mailto:", "tel:", "javascript:", "#")):
        return False
    return any(x in h for x in PROFILE_HINTS)

def score_grid_html(html: str) -> int:
    soup = BeautifulSoup(html or "", "lxml")
    a = soup.select("a[href]")
    prof = 0
    img = len(soup.select("img"))
    for link in a:
        href = (link.get("href") or "").strip()
        if looks_like_profile_href(href):
            prof += 1
    txt = soup.get_text(" ")
    score = prof * 10 + img + len(PHONE_RE.findall(txt)) * 5
    if "/list/searchalpha/" in (html or "").lower():
        score += 200
    return score

def pick_best_context(page: Page) -> Tuple[Page | Frame, str]:
    page.wait_for_timeout(1200)
    best: Page | Frame = page
    best_score = score_grid_html(page.content())
    best_url = page.url
    for fr in page.frames:
        if fr == page.main_frame:
            continue
        try:
            sc = score_grid_html(fr.content())
            if sc > best_score:
                best_score = sc
                best = fr
                best_url = fr.url or page.url
        except Exception:
            continue
    return best, best_url

def extract_profile_links(ctx: Page | Frame, base_url: str) -> List[Tuple[str,str]]:
    soup = BeautifulSoup(ctx.content(), "lxml")
    items: List[Tuple[str,str]] = []

    for a in soup.select("a[href]"):
        href = (a.get("href") or "").strip()
        if not looks_like_profile_href(href):
            continue
        u = href if href.startswith("http") else norm_url(base_url, href)
        if not u:
            continue

        name = clean(a.get_text(" "))
        if not name:
            img = a.find("img")
            if img:
                name = clean(img.get("alt") or img.get("title") or "")
        if not name:
            name = clean(a.get("aria-label") or a.get("title") or "")
        items.append((u, name))

    seen: Set[str] = set()
    out: List[Tuple[str,str]] = []
    for u, n in items:
        if u.lower() in seen:
            continue
        seen.add(u.lower())
        out.append((u, n))
    return out

def parse_profile(html: str, url: str, fallback_name: str) -> Member:
    soup = BeautifulSoup(html or "", "lxml")
    m = Member()
    m.profile_url = url

    h = soup.find(["h1","h2"])
    if h and clean(h.get_text(" ")):
        m.name = clean(h.get_text(" "))
    if not m.name:
        title = soup.title.get_text(" ") if soup.title else ""
        title = clean(title)
        for suf in [" - ", " | "]:
            if suf in title:
                title = title.split(suf)[0].strip()
                break
        m.name = title
    if not m.name:
        m.name = fallback_name

    text = soup.get_text(" ")
    pm = PHONE_RE.search(text)
    if pm:
        m.phone = clean(pm.group(0))

    mail = soup.select_one('a[href^="mailto:"]')
    if mail:
        m.email = clean((mail.get("href") or "").replace("mailto:", ""))

    website = ""
    for a in soup.select("a[href]"):
        href = (a.get("href") or "").strip()
        if not href:
            continue
        if href.startswith("http") and urlparse(href).netloc and urlparse(href).netloc.lower() != urlparse(url).netloc.lower():
            t = clean(a.get_text(" ")).lower()
            if t in ("website","visit site","web","site") or ("http" in href):
                website = href
                break
    m.website = website

    addr = ""
    addr_node = soup.select_one('[itemprop="address"], .address, .listing-address, .gz-address')
    if addr_node:
        addr = clean(addr_node.get_text(" "))
    if not addr:
        cand = []
        for div in soup.find_all(["div","p","span"], limit=400):
            t = clean(div.get_text(" "))
            if len(t) < 10 or len(t) > 200:
                continue
            if re.search(r"\b[A-Z]{2}\s+\d{5}\b", t) or re.search(r"\bCA\s+\d{5}\b", t):
                cand.append(t)
        if cand:
            addr = cand[0]
    m.address = addr
    return m

def write_csv(path: str, rows: List[Member]):
    if not rows:
        # still write header for consistency
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(asdict(Member()).keys()))
            w.writeheader()
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(rows[0]).keys()))
        w.writeheader()
        for r in rows:
            w.writerow(asdict(r))

def discover_alpha_urls(ctx: Page | Frame, base_url: str) -> List[str]:
    """
    Discover A–Z alpha directory links from the current page.

    Strategy:
    - Look for links whose href matches /list/searchalpha/<letter>
    - If none found but current URL is a searchalpha URL, generate A–Z by pattern using the same base path and query params
    """
    html = ctx.content()
    soup = BeautifulSoup(html or "", "lxml")
    found: List[str] = []
    for a in soup.select("a[href]"):
        href = (a.get("href") or "").strip()
        if not href:
            continue
        m = SEARCHALPHA_RE.search(href)
        if m:
            u = href if href.startswith("http") else norm_url(base_url, href)
            if u:
                found.append(u)

    # dedupe
    out: List[str] = []
    seen = set()
    for u in found:
        k = u.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(u)

    # If the page exposed a real A–Z nav, we should see many links.
    # Some sites only include the current letter in the DOM (len == 1),
    # so in that case we fall back to pattern generation below.
    if len(out) >= 2:
        # sort by letter if possible
        def key(u: str):
            mm = SEARCHALPHA_RE.search(u)
            return (mm.group(1).lower() if mm else "z")
        out.sort(key=key)
        return out

    # fallback generation if current URL contains /list/searchalpha/<letter>
    cur = base_url
    mm = SEARCHALPHA_RE.search(cur)
    if not mm:
        return []

    # Keep query params (some sites use ?q=a&o=&)
    parts = urlsplit(cur)
    qs = parse_qs(parts.query, keep_blank_values=True)

    # Build a base path replacing the letter with "{letter}"
    path = parts.path
    path = SEARCHALPHA_RE.sub("/list/searchalpha/{letter}", path)

    gen: List[str] = []
    for ch in string.ascii_lowercase:
        new_path = path.format(letter=ch)
        # If site uses q=<letter>, keep it aligned
        if "q" in qs:
            qs2 = dict(qs)
            qs2["q"] = [ch]
            query = urlencode(qs2, doseq=True)
        else:
            query = parts.query
        gen_url = urlunsplit((parts.scheme, parts.netloc, new_path, query, parts.fragment))
        gen.append(gen_url)

    return gen

def click_next(ctx: Page | Frame) -> bool:
    current_url = ctx.url if hasattr(ctx, "url") else ctx.page.url
    allowed_host = urlparse(current_url).netloc.lower()

    selectors = [
        'a[rel="next"]',
        'a:has-text("Next")',
        'button:has-text("Next")',
        'a:has-text("›")',
        'a:has-text(">")',
        'li.next a',
        'a.next',
        'button.next',
    ]

    for sel in selectors:
        loc = ctx.locator(sel)
        if loc.count() == 0:
            continue
        try:
            el = loc.first
            aria = el.get_attribute("aria-disabled")
            if aria and aria.lower() == "true":
                continue
            if el.get_attribute("disabled") is not None:
                continue
            el.click()
            ctx.page.wait_for_timeout(900)
            now = ctx.url if hasattr(ctx, "url") else ctx.page.url
            if urlparse(now).netloc.lower() != allowed_host:
                log_error("pagination", "Off-site navigation blocked")
                return False
            return True
        except Exception:
            continue

    # Numeric paging fallback
    try:
        active = ctx.locator("li.active a, .pagination .active a, a.active")
        if active.count():
            cur = (active.first.text_content() or "").strip()
            if cur.isdigit():
                target = str(int(cur) + 1)
                loc = ctx.locator(f'a:has-text("{target}")')
                if loc.count():
                    loc.first.click()
                    ctx.page.wait_for_timeout(900)
                    now = ctx.url if hasattr(ctx, "url") else ctx.page.url
                    if urlparse(now).netloc.lower() != allowed_host:
                        log_error("pagination", "Off-site navigation blocked")
                        return False
                    return True
    except Exception:
        pass

    return False

def scrape_one_directory(page: Page, profile_page: Page, start_url: str, out: str, seen_profiles: Set[str], rows: List[Member],
                         max_pages: int, max_profiles: int, delay: float, timeout_ms: int, source_url: str):
    safe_goto(page, start_url, wait_until="load")
    page.wait_for_timeout(1200)
    active, base_url = pick_best_context(page)

    for page_i in range(1, max_pages + 1):
        links = extract_profile_links(active, base_url)
        if not links:
            break

        added = 0
        for prof_url, guess_name in links:
            if len(rows) >= max_profiles:
                return
            key = prof_url.lower()
            if key in seen_profiles:
                continue
            seen_profiles.add(key)

            try:
                safe_goto(profile_page, prof_url, wait_until="load")
                profile_page.wait_for_timeout(600)
                m = parse_profile(profile_page.content(), prof_url, guess_name)
                m.source_url = source_url
                if not m.name:
                    continue
                rows.append(m)
                added += 1
            except Exception:
                continue

            if delay:
                time.sleep(delay)

        log_info(f"Page: profiles added {added}, total {len(rows)}")
        write_csv(out, rows)

        if len(rows) >= max_profiles:
            return

        if not click_next(active):
            break

        if delay:
            time.sleep(delay)

def scrape(url: str, out: str, headless: bool, max_pages: int, max_profiles: int, delay: float, timeout_ms: int, alpha: bool):
    seen_profiles: Set[str] = set()
    rows: List[Member] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(timeout_ms)

        profile_page = context.new_page()
        profile_page.set_default_timeout(timeout_ms)

        # Load once to discover alpha links if any
        safe_goto(page, url, wait_until="load")
        page.wait_for_timeout(1200)
        active, base_url = pick_best_context(page)

        alpha_urls = discover_alpha_urls(active, base_url) if alpha else []
        if alpha_urls:
            log_info(f"Detected alpha directory with {len(alpha_urls)} letters.")
            start_urls = alpha_urls
        else:
            start_urls = [url]

        try:
            for i, start_url in enumerate(start_urls, start=1):
                if len(start_urls) > 1:
                    letter = SEARCHALPHA_RE.search(start_url)
                    tag = f"{letter.group(1).lower()}" if letter else str(i)
                    log_info(f"[alpha {tag}] {start_url}")
                scrape_one_directory(page, profile_page, start_url, out, seen_profiles, rows, max_pages, max_profiles, delay, timeout_ms, source_url=url)
                write_csv(out, rows)
                if len(rows) >= max_profiles:
                    log_info("Reached --max-profiles limit. Stopping.")
                    break
        except KeyboardInterrupt:
            log_info("Interrupted. Saving partial results.")

        write_csv(out, rows)
        log_summary({"rows_saved": len(rows), "output_file": out})
        browser.close()

def main():
    ap = argparse.ArgumentParser(description="Grid/Tile directory harvester (ChamberMaster/GrowthZone-style)")
    ap.add_argument("url")
    ap.add_argument("--out", default="members.csv")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--max-pages", type=int, default=200, help="Max pages per letter/directory")
    ap.add_argument("--max-profiles", type=int, default=200000, help="Safety cap on total profiles to visit")
    ap.add_argument("--delay", type=float, default=0.8)
    ap.add_argument("--timeout-ms", type=int, default=60000)
    ap.add_argument("--alpha", action="store_true", help="Enable A–Z alpha traversal when /searchalpha/ is detected")
    args = ap.parse_args()

    scrape(args.url, args.out, args.headless, args.max_pages, args.max_profiles, max(0.0,args.delay), max(5000,args.timeout_ms), alpha=args.alpha)

if __name__ == "__main__":
    main()
