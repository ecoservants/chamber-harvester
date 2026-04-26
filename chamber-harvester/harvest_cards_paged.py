#!/usr/bin/env python3
"""Chamber Directory Harvester (Playwright, browser-first)

Notes
- These tools are intended for public member directories.
- Many chambers embed listings in iframes and paginate via buttons or numeric page links.
- Output is CSV and autosaves each page. Ctrl+C writes partial results.

Install
  pip install playwright beautifulsoup4 lxml
  python -m playwright install

"""

from __future__ import annotations
import argparse, csv, re, time
from dataclasses import dataclass, asdict
from typing import List, Optional, Tuple, Set
from urllib.parse import urljoin, urldefrag, urlparse

from harvest_common import choose_best_website, clean_address, normalize_url, row_key, should_keep_row, host_of, require_safe_url, safe_goto

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, Page, Frame

PHONE_RE = re.compile(r"(?:(?:\+?1\s*)?(?:\(\s*\d{3}\s*\)|\d{3})[-.\s]*)\d{3}[-.\s]*\d{4}")
BAD_LINK_RE = re.compile(r"^(javascript:|mailto:|tel:|#)", re.I)

@dataclass
class Card:
    name: str = ""
    phone: str = ""
    address: str = ""
    website: str = ""
    profile_url: str = ""
    source_url: str = ""

def clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def norm_url(base: str, href: str) -> str:
    return normalize_url(base, href)

def score_card_html(html: str) -> int:
    soup = BeautifulSoup(html or "", "lxml")
    txt = soup.get_text(" ").lower()
    score = 0
    # Card-y signals
    score += txt.count("learn more") * 30
    score += txt.count("visit site") * 20
    score += txt.count("member since") * 10
    score += len(soup.select("a[href]"))
    score += len(PHONE_RE.findall(soup.get_text(" "))) * 25
    return score

def pick_best_context(page: Page) -> Tuple[Page | Frame, str]:
    page.wait_for_timeout(1200)
    best_ctx: Page | Frame = page
    best_score = score_card_html(page.content())
    best_url = page.url
    for fr in page.frames:
        if fr == page.main_frame:
            continue
        try:
            sc = score_card_html(fr.content())
            if sc > best_score:
                best_score = sc
                best_ctx = fr
                best_url = fr.url or page.url
        except Exception:
            continue
    return best_ctx, best_url

def extract_cards(soup: BeautifulSoup, base_url: str) -> List[Card]:
    cards: List[Card] = []
    chamber_host = host_of(base_url)
    seen_blocks = set()
    anchors = soup.select('a[href]')
    for a in anchors:
        t = clean(a.get_text(" ")).lower()
        if t not in ("learn more", "visit site", "website", "visit website"):
            continue
        container = a
        chosen = None
        for _ in range(7):
            if not getattr(container, 'parent', None):
                break
            container = container.parent
            links = container.select('a[href]') if hasattr(container, 'select') else []
            if 2 <= len(links) <= 20:
                chosen = container
                break
        container = chosen or container
        cid = id(container)
        if cid in seen_blocks:
            continue
        seen_blocks.add(cid)
        block_text = clean(container.get_text(" "))
        if not block_text or len(block_text) < 10:
            continue

        name = ""
        h = container.find(["h1", "h2", "h3", "h4", "strong"])
        if h:
            name = clean(h.get_text(" "))
        if not name:
            for cand in container.select('a[href], span, div, p')[:6]:
                txt = clean(cand.get_text(" "))
                if txt and len(txt) <= 90 and txt.lower() not in ("learn more", "visit site", "website", "visit website"):
                    name = txt
                    break

        phone = ""
        m = PHONE_RE.search(block_text)
        if m:
            phone = clean(m.group(0))

        website_candidates = []
        profile = ""
        for link in container.select("a[href]"):
            lt = clean(link.get_text(" "))
            href = link.get("href", "")
            if not href:
                continue
            absu = href if href.startswith("http") else norm_url(base_url, href)
            if not absu:
                continue
            if lt.lower() in ("learn more", "details", "view profile"):
                profile = absu
            website_candidates.append((absu, lt))

        website = choose_best_website(website_candidates, chamber_host=chamber_host, business_name=name)

        lines = [clean(x) for x in container.stripped_strings]
        lines = [x for x in lines if x.lower() not in ("learn more", "visit site", "website", "visit website")]
        address = clean_address(" ".join(lines[1:5])) if len(lines) > 1 else ""

        c = Card(name=name, phone=phone, address=address, website=website, profile_url=profile)
        if should_keep_row(c.name, c.phone, c.address, c.profile_url, c.website):
            cards.append(c)

    uniq = {}
    for c in cards:
        k = row_key(c.name, c.phone, c.address, c.profile_url)
        if c.name and k not in uniq:
            uniq[k] = c
    return list(uniq.values())

def write_csv(path: str, rows: List[Card]):
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(rows[0]).keys()))
        w.writeheader()
        for r in rows:
            w.writerow(asdict(r))

def click_next_or_number(ctx: Page | Frame, timeout_ms: int, current_page: int) -> bool:
    # Off-site guard uses current ctx url
    current_url = ctx.url if hasattr(ctx, "url") else ctx.page.url
    allowed_host = urlparse(current_url).netloc.lower()

    # 1) Try Next
    for sel in ['a:has-text("Next")','button:has-text("Next")','a[rel="next"]','a:has-text("›")','a:has-text(">")']:
        loc = ctx.locator(sel)
        if loc.count():
            try:
                loc.first.click()
                ctx.page.wait_for_timeout(900)
                now = ctx.url if hasattr(ctx, "url") else ctx.page.url
                if urlparse(now).netloc.lower() != allowed_host:
                    print("Off-site navigation blocked. Stopping pagination.")
                    return False
                return True
            except Exception:
                pass

    # 2) Try numeric page links: click current_page+1
    target = str(current_page + 1)
    loc = ctx.locator(f'a:has-text("{target}")')
    if loc.count():
        try:
            loc.first.click()
            ctx.page.wait_for_timeout(900)
            now = ctx.url if hasattr(ctx, "url") else ctx.page.url
            if urlparse(now).netloc.lower() != allowed_host:
                print("Off-site navigation blocked. Stopping pagination.")
                return False
            return True
        except Exception:
            return False

    return False

def scrape(url: str, out: str, headless: bool, max_pages: int, delay: float, timeout_ms: int):
    seen: Set[str] = set()
    rows: List[Card] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(timeout_ms)
        safe_goto(page, url, wait_until="load")
        page.wait_for_timeout(1200)

        active, base_url = pick_best_context(page)
        print(f"Using context URL: {base_url}")

        try:
            current_page_num = 1
            for i in range(1, max_pages + 1):
                soup = BeautifulSoup(active.content(), "lxml")
                page_cards = extract_cards(soup, base_url)
                added = 0
                for c in page_cards:
                    c.source_url = url
                    k = row_key(c.name, c.phone, c.address, c.profile_url)
                    if not c.name or k in seen:
                        continue
                    seen.add(k)
                    rows.append(c)
                    added += 1

                print(f"[page {i}] added {added}, total {len(rows)}")
                write_csv(out, rows)

                if not click_next_or_number(active, timeout_ms, current_page_num):
                    break
                current_page_num += 1
                if delay:
                    time.sleep(delay)
        except KeyboardInterrupt:
            print("\nInterrupted. Saving partial results...")
        write_csv(out, rows)
        print(f"Saved {len(rows)} rows -> {out}")
        browser.close()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--out", default="members.csv")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--max-pages", type=int, default=5000)
    ap.add_argument("--delay", type=float, default=0.8)
    ap.add_argument("--timeout-ms", type=int, default=60000)
    args = ap.parse_args()
    scrape(args.url, args.out, args.headless, args.max_pages, max(0.0,args.delay), max(5000,args.timeout_ms))

if __name__ == "__main__":
    main()
