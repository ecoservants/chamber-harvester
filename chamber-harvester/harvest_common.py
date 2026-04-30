from __future__ import annotations

import csv
import ipaddress
import re
from typing import Dict, List, Sequence, Tuple
from urllib.parse import parse_qsl, urlencode, urljoin, urldefrag, urlparse, urlunparse

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(r"(?:(?:\+?1\s*)?(?:\(\s*\d{3}\s*\)|\d{3})[-.\s]*)\d{3}[-.\s]*\d{4}")
ZIP_RE = re.compile(r"\b\d{5}(?:-\d{4})?\b")

BAD_WEBSITE_HOST_PARTS = {
    "userway.org", "facebook.com", "fb.com", "linkedin.com", "instagram.com", "twitter.com",
    "x.com", "youtube.com", "youtu.be", "google.com", "googleadservices.com", "g.page",
    "maps.apple.com", "mapquest.com", "paypal.com", "venmo.com", "cash.app",
}
BAD_WEBSITE_PATH_HINTS = (
    "/donate", "/share", "/sharer", "/maps", "/map", "/directions", "/events", "/join",
    "/member-application", "/membership-application", "/business-directory-search",
)
SUSPICIOUS_NAME_PATTERNS = [
    re.compile(p, re.I)
    for p in [
        r"^directory$", r"^contact$", r"^member application$", r"^business directory search$",
        r"^login$", r"^join$", r"^apply$", r"^quincy chamber of commerce: member contact form$",
        r"^search$", r"^members?$", r"^advertise$", r"^home$",
    ]
]
UNSAFE_URL_SCHEMES = {"file", "javascript", "data", "vbscript", "about", "chrome", "chrome-extension"}
PRIVATE_HOSTNAMES = {"localhost", "local", "0.0.0.0"}


def clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def is_safe_url(url: str) -> Tuple[bool, str]:
    """Validate URLs before local-browser navigation."""
    raw = (url or "").strip()
    if not raw:
        return False, "empty URL"
    try:
        parsed = urlparse(raw)
    except Exception:
        return False, "could not parse URL"
    scheme = (parsed.scheme or "").lower()
    if scheme not in {"http", "https"} or scheme in UNSAFE_URL_SCHEMES:
        return False, f"blocked URL scheme: {scheme or '(missing)'}"
    host = (parsed.hostname or "").strip().lower().rstrip(".")
    if not host:
        return False, "missing hostname"
    if host in PRIVATE_HOSTNAMES or host.endswith(".localhost") or host.endswith(".local"):
        return False, f"blocked local hostname: {host}"
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            return False, f"blocked private/local IP: {host}"
    except ValueError:
        pass
    return True, ""


def require_safe_url(url: str, label: str = "URL") -> str:
    ok, reason = is_safe_url(url)
    if not ok:
        raise ValueError(f"Unsafe {label}: {reason} ({url!r})")
    return url


def safe_goto(page, url: str, *args, **kwargs):
    require_safe_url(url, "navigation URL")
    return page.goto(url, *args, **kwargs)


def normalize_url(base: str, href: str) -> str:
    if not href:
        return ""
    href = href.strip()
    if not href or href.lower().startswith(("javascript:", "mailto:", "tel:", "#", "data:", "file:", "vbscript:")):
        return ""
    u = urljoin(base, href)
    u, _ = urldefrag(u)
    parsed = urlparse(u)
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if not k.lower().startswith(("utm_", "fbclid", "gclid"))]
    cleaned = urlunparse((parsed.scheme.lower(), parsed.netloc, parsed.path.rstrip("/") or parsed.path, parsed.params, urlencode(query), ""))
    ok, _ = is_safe_url(cleaned)
    return cleaned if ok else ""


def normalize_name(name: str) -> str:
    s = clean_text(name).lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return clean_text(s)


def normalize_email(email: str) -> str:
    m = EMAIL_RE.search(email or "")
    return m.group(0).lower() if m else ""


def normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D+", "", phone or "")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits if len(digits) == 10 else ""


def host_of(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def domain_of_email(email: str) -> str:
    email = normalize_email(email)
    return email.split("@", 1)[1] if "@" in email else ""


def is_suspicious_name(name: str) -> bool:
    s = clean_text(name)
    if not s or len(s) < 2:
        return True
    return any(p.search(s) for p in SUSPICIOUS_NAME_PATTERNS)


def score_website(url: str, chamber_host: str = "", business_name: str = "", link_text: str = "") -> int:
    if not url:
        return -999
    parsed = urlparse(url)
    host = parsed.netloc.lower().replace("www.", "")
    path = parsed.path.lower()
    score = 0
    if parsed.scheme not in ("http", "https"):
        return -999
    if not host:
        return -999
    if chamber_host and (host == chamber_host or host.endswith("." + chamber_host) or chamber_host.endswith("." + host)):
        score -= 70
    if any(host == bad or host.endswith("." + bad) for bad in BAD_WEBSITE_HOST_PARTS):
        score -= 80
    if any(h in path for h in BAD_WEBSITE_PATH_HINTS):
        score -= 50
    if link_text:
        lt = clean_text(link_text).lower()
        if any(k in lt for k in ["website", "visit website", "visit site", "web"]):
            score += 25
        if any(k in lt for k in ["facebook", "instagram", "linkedin", "map", "directions", "donate", "share"]):
            score -= 40
    if business_name:
        tokens = [t for t in normalize_name(business_name).split() if len(t) >= 4][:4]
        if tokens and any(t in host or t in path for t in tokens):
            score += 15
    if host.count(".") >= 1:
        score += 8
    if re.search(r"\.(html?|php|aspx?)$", path):
        score -= 5
    return score


def choose_best_website(candidates: Sequence[Tuple[str, str]], chamber_host: str = "", business_name: str = "") -> str:
    best_url = ""
    best_score = -999
    for href, text in candidates:
        url = normalize_url("", href) if href.startswith("http") else href
        sc = score_website(url, chamber_host=chamber_host, business_name=business_name, link_text=text)
        if sc > best_score:
            best_score = sc
            best_url = url
    return best_url if best_score >= 0 else ""


def clean_address(text: str) -> str:
    s = clean_text(text)
    if not s:
        return ""
    s = re.sub(r"\b(?:fax|phone|tel|telephone)\b.*$", "", s, flags=re.I)
    s = re.sub(PHONE_RE, "", s)
    return clean_text(s.strip(" ,;-"))


def maybe_extract_email(text: str) -> str:
    return normalize_email(text)


def should_keep_row(name: str, phone: str = "", address: str = "", profile_url: str = "", website: str = "", email: str = "") -> bool:
    if is_suspicious_name(name):
        return False
    signals = 0
    if normalize_phone(phone): signals += 1
    if clean_address(address): signals += 1
    if profile_url: signals += 1
    if website: signals += 1
    if normalize_email(email): signals += 1
    return signals >= 1


def normalize_profile_url(url: str) -> str:
    return normalize_url("", url)


def row_key(name: str, phone: str = "", address: str = "", profile_url: str = "") -> str:
    prof = normalize_profile_url(profile_url)
    if prof:
        return "p:" + prof
    return "n:%s|ph:%s|a:%s" % (normalize_name(name), normalize_phone(phone), clean_address(address).lower())


def maybe_blank_chamber_email(email: str, chamber_host: str, profile_url: str = "") -> str:
    email = normalize_email(email)
    if not email or not chamber_host:
        return email
    ed = domain_of_email(email)
    prof_host = host_of(profile_url)
    if ed == chamber_host and prof_host and prof_host != chamber_host:
        return ""
    return email


def load_csv_quality(path: str, chamber_host: str = "") -> Tuple[int, int, Dict[str, int]]:
    rows = 0; duplicates = 0; bad_names = 0; repeated_site_penalty = 0; repeated_email_penalty = 0; complete = 0
    seen = set(); website_counts: Dict[str, int] = {}; email_counts: Dict[str, int] = {}
    try:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                rows += 1
                name = r.get("name", ""); phone = r.get("phone", ""); address = r.get("address", "")
                website = r.get("website", ""); email = r.get("email", ""); profile = r.get("profile_url", "")
                k = row_key(name, phone, address, profile)
                if k in seen: duplicates += 1
                else: seen.add(k)
                if is_suspicious_name(name): bad_names += 1
                wh = host_of(website)
                if wh: website_counts[wh] = website_counts.get(wh, 0) + 1
                ed = domain_of_email(email)
                if ed: email_counts[ed] = email_counts.get(ed, 0) + 1
                if name and (phone or address or website or email or profile): complete += 1
    except Exception:
        return 0, 0, {"duplicates": 0, "bad_names": 0, "complete": 0}
    for h, n in website_counts.items():
        if h == chamber_host and n > 2: repeated_site_penalty += n
    for d, n in email_counts.items():
        if d == chamber_host and n > 2: repeated_email_penalty += n
    quality = rows * 10 + complete * 4 - duplicates * 15 - bad_names * 20 - repeated_site_penalty * 10 - repeated_email_penalty * 10
    return rows, quality, {"duplicates": duplicates, "bad_names": bad_names, "complete": complete}
    def open_csv_writer(path: str, fieldnames: list):
    """
    Opens a CSV file for incremental (append-safe) writing.
    Writes the header only if the file is new or empty.
    Returns (file_handle, csv.DictWriter).
    """
    import os
    file_exists = os.path.isfile(path) and os.path.getsize(path) > 0
    fh = open(path, "a", newline="", encoding="utf-8")
    writer = csv.DictWriter(fh, fieldnames=fieldnames)
    if not file_exists:
        writer.writeheader()
    return fh, writer
