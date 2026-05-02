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
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, Page, Frame

from harvest_common import normalize_url, require_safe_url, safe_goto, log_info, log_error, log_summary, log_page_visit, log_row_extracted

BAD_LINK_RE = re.compile(r"^(javascript:|mailto:|tel:|#)", re.I)

@dataclass
class Row:
    name: str = ""
    industry: str = ""
    phone: str = ""
    website: str = ""
    profile_url: str = ""
    source_url: str = ""

def clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def norm_url(base: str, href: str) -> str:
    return normalize_url(base, href)

def score_table_html(html: str) -> int:
    soup = BeautifulSoup(html or "", "lxml")
    rows = len(soup.select("table tr"))
    headers = " ".join([clean(th.get_text(" ")) for th in soup.select("table th")]).lower()
    score = rows
    if "company" in headers or "business" in headers: score += 200
    if "industry" in headers or "category" in headers: score += 100
    if "phone" in headers: score += 100
    if "web" in headers or "website" in headers: score += 100
    return score

def pick_best_context(page: Page) -> Tuple[Page | Frame, str]:
    page.wait_for_timeout(1200)
    best_ctx: Page | Frame = page
    best_score = score_table_html(page.content())
    best_url = page.url
    for fr in page.frames:
        if fr == page.main_frame:
            continue
        try:
            sc = score_table_html(fr.content())
            if sc > best_score:
                best_score = sc
                best_ctx = fr
                best_url = fr.url or page.url
        except Exception:
            continue
    return best_ctx, best_url

def find_best_table(soup: BeautifulSoup):
    best = None
    best_score = -1
    for t in soup.find_all("table"):
        headers = [clean(th.get_text(" ")) for th in t.select("th")]
        if not headers:
            continue
        header_blob = " ".join(headers).lower()
        if not any(k in header_blob for k in ["company","business","member","industry","phone","web","website"]):
            continue
        rows = t.select("tr")
        if len(rows) < 5:
            continue
        score = len(rows)
        if "company" in header_blob or "business" in header_blob:
            score += 50
        if "phone" in header_blob:
            score += 20
        if "web" in header_blob or "website" in header_blob:
            score += 20
        if score > best_score:
            best_score = score
            best = t
    return best

def row_from_table(headers: List[str], cells: List[str], hrefs: List[str], base_url: str) -> Row:
    idx = {h.lower(): i for i, h in enumerate(headers)}
    def get_cell(*names):
        for n in names:
            i = idx.get(n.lower())
            if i is not None and i < len(cells):
                return cells[i]
        return ""
    def get_href(*names):
        for n in names:
            i = idx.get(n.lower())
            if i is not None and i < len(hrefs):
                return hrefs[i]
        return ""
    r = Row()
    r.name = get_cell("Company","Business","Member","Organization")
    r.industry = get_cell("Industry","Category","Type")
    r.phone = get_cell("Phone","Telephone")
    web_href = get_href("Web","Website")
    web_text = get_cell("Web","Website")
    if web_href:
        r.website = web_href if web_href.startswith("http") else norm_url(base_url, web_href)
    elif web_text.startswith("http"):
        r.website = web_text
    prof = get_href("Company","Business","Member","Organization")
    if prof:
        r.profile_url = prof if prof.startswith("http") else norm_url(base_url, prof)
    return r

def write_csv(path: str, rows: List[Row]):
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(rows[0]).keys()))
        w.writeheader()
        for r in rows:
            w.writerow(asdict(r))

def click_next(ctx: Page | Frame, timeout_ms: int) -> bool:
    # Works inside page or frame
    selectors = [
        'a[rel="next"]',
        'a:has-text("Next")',
        'button:has-text("Next")',
        'input[type="submit"][value*="Next" i]',
        'input[type="button"][value*="Next" i]',
        'a:has-text("›")',
        'a:has-text(">")',
        'button:has-text("›")',
        'button:has-text(">")',
    ]
    current_url = ctx.url if hasattr(ctx, "url") else ctx.page.url
    allowed_host = urlparse(current_url).netloc.lower()

    for sel in selectors:
        loc = ctx.locator(sel)
        if loc.count() == 0:
            continue
        try:
            el = loc.first
            if el.get_attribute("disabled") is not None:
                continue
            aria = el.get_attribute("aria-disabled")
            if aria and aria.lower() == "true":
                continue
            el.click()
            ctx.page.wait_for_timeout(900)
            # Off-site guard
            now = ctx.url if hasattr(ctx, "url") else ctx.page.url
            if urlparse(now).netloc.lower() != allowed_host:
                log_error("pagination", "Off-site navigation blocked")
                return False
            return True
        except Exception:
            continue
    return False

def scrape(url: str, out: str, headless: bool, max_pages: int, delay: float, timeout_ms: int):
    seen: Set[str] = set()
    rows: List[Row] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.set_default_timeout(timeout_ms)
        safe_goto(page, url, wait_until="load")
        page.wait_for_timeout(1200)

        active, base_url = pick_best_context(page)
        log_info(f"Using context URL: {base_url}")

        try:
            for i in range(1, max_pages + 1):
                soup = BeautifulSoup(active.content(), "lxml")
                table = find_best_table(soup)
                if not table:
                    log_error("extraction", "No suitable table found")
                    break

                headers = [clean(th.get_text(" ")) for th in table.select("th")]
                added = 0
                for tr in table.select("tr"):
                    tds = tr.find_all(["td","th"])
                    if not tds:
                        continue
                    cells = [clean(td.get_text(" ")) for td in tds]
                    if headers and [c.lower() for c in cells] == [h.lower() for h in headers]:
                        continue
                    if sum(1 for c in cells if c) <= 1:
                        continue
                    hrefs = []
                    for td in tds:
                        a = td.find("a", href=True)
                        hrefs.append((a["href"].strip() if a else ""))
                    r = row_from_table(headers, cells, hrefs, base_url)
                    r.source_url = url
                    if not r.name:
                        continue
                    k = (r.name + "|" + (r.phone or "") + "|" + (r.website or "")).lower()
                    if k in seen:
                        continue
                    seen.add(k)
                    rows.append(r)
                    added += 1

                log_info(f"Page {i}: added {added}, total {len(rows)}")
                write_csv(out, rows)

                if not click_next(active, timeout_ms):
                    break
                if delay:
                    time.sleep(delay)
        except KeyboardInterrupt:
            log_info("Interrupted. Saving partial results...")
        write_csv(out, rows)
        log_summary({"rows_saved": len(rows), "output_file": out})
        browser.close()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--out", default="members.csv")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--max-pages", type=int, default=5000)
    ap.add_argument("--delay", type=float, default=0.6)
    ap.add_argument("--timeout-ms", type=int, default=60000)
    args = ap.parse_args()
    scrape(args.url, args.out, args.headless, args.max_pages, max(0.0,args.delay), max(5000,args.timeout_ms))

if __name__ == "__main__":
    main()
