#!/usr/bin/env python3
"""Wrapper script that auto-selects the best chamber harvester.

Usage:
  python run_harvest.py "<directory_url>" --out results.csv [--headless]

How it works:
- Runs short probe scrapes with each supported harvester
- Chooses the harvester that returns the most rows
- Runs a full scrape with the selected harvester

Notes:
- Use --force <name> to skip probing
- For A–Z directories (URLs containing /searchalpha/), the grid harvester supports --alpha
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

from harvest_common import load_csv_quality, require_safe_url, log_info, log_error, log_summary

HERE = Path(__file__).resolve().parent

# (name, filename)
CANDIDATES: List[Tuple[str, str]] = [
    ("table", "harvest_table_iframe.py"),
    ("cards", "harvest_cards_paged.py"),
    ("grid", "harvest_grid_directory.py"),
    ("atlas", "harvest_atlas_directory.py"),
    ("chamberdata", "harvest_chamberdata_az.py"),
]

# Harvesters that accept --max-pages
SUPPORTS_MAX_PAGES = {"table", "cards", "grid"}

DEFAULT_PROBE_MAX_PAGES = 3


def count_csv_rows(path: Path) -> int:
    """Return number of data rows (excluding header)."""
    try:
        if not path.exists() or path.stat().st_size == 0:
            return 0

        # Fast line count in binary mode (works for huge CSVs)
        with path.open("rb") as f:
            lines = 0
            for buf in iter(lambda: f.read(1024 * 1024), b""):
                lines += buf.count(b"\n")

        # Best-effort: assume header exists if >= 1 line
        return max(0, lines - 1)
    except Exception:
        return 0


def run_script_capture(script: Path, args: List[str], timeout_sec: Optional[int]) -> subprocess.CompletedProcess:
    """Run a harvester, capturing stdout/stderr."""
    cmd = [sys.executable, str(script)] + args
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
        env=os.environ.copy(),
    )


def run_script_stream(script: Path, args: List[str]) -> int:
    """Run a harvester, streaming stdout/stderr to the console."""
    cmd = [sys.executable, str(script)] + args
    proc = subprocess.Popen(cmd, stdout=sys.stdout, stderr=sys.stderr, text=True, env=os.environ.copy())
    try:
        return proc.wait()
    except KeyboardInterrupt:
        try:
            proc.terminate()
        except Exception:
            pass
        raise


def run_probe(
    name: str,
    script: Path,
    url: str,
    headless: bool,
    delay: float,
    timeout_ms: int,
    probe_timeout_sec: int,
    extra_args: Optional[List[str]] = None,
) -> Tuple[str, int, int, str, Dict[str, int]]:
    """Return (name, rows, quality_score, combined_output, stats) for a quick probe."""
    tmp_out = HERE / f"_probe_{script.stem}.csv"
    try:
        if tmp_out.exists():
            tmp_out.unlink()
    except Exception:
        pass

    args: List[str] = [url, "--out", str(tmp_out)]
    if headless:
        args.append("--headless")
    args += ["--delay", str(delay), "--timeout-ms", str(timeout_ms)]

    if name in SUPPORTS_MAX_PAGES:
        args += ["--max-pages", str(DEFAULT_PROBE_MAX_PAGES)]

    if extra_args:
        args += extra_args

    try:
        proc = run_script_capture(script, args, timeout_sec=probe_timeout_sec)
        out = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            rows = 0
            quality = 0
            stats = {"duplicates": 0, "bad_names": 0, "complete": 0}
        else:
            rows, quality, stats = load_csv_quality(str(tmp_out), chamber_host=urlparse(url).netloc.lower().replace("www.", ""))
    except subprocess.TimeoutExpired as e:
        out = f"[probe timeout after {probe_timeout_sec}s]\n" + (getattr(e, "stdout", "") or "") + (getattr(e, "stderr", "") or "")
        rows = 0
        quality = 0
        stats = {"duplicates": 0, "bad_names": 0, "complete": 0}
    except KeyboardInterrupt:
        raise
    except Exception as e:
        out = f"[probe error] {e}"
        rows = 0
        quality = 0
        stats = {"duplicates": 0, "bad_names": 0, "complete": 0}
    finally:
        try:
            if tmp_out.exists():
                tmp_out.unlink()
        except Exception:
            pass

    return name, rows, quality, out, stats


def run_full(
    name: str,
    script: Path,
    url: str,
    out_csv: Path,
    headless: bool,
    max_pages: int,
    delay: float,
    timeout_ms: int,
    extra_args: Optional[List[str]] = None,
) -> int:
    args: List[str] = [url, "--out", str(out_csv)]
    if headless:
        args.append("--headless")
    args += ["--delay", str(delay), "--timeout-ms", str(timeout_ms)]

    if name in SUPPORTS_MAX_PAGES and max_pages:
        args += ["--max-pages", str(max_pages)]

    if extra_args:
        args += extra_args

    return run_script_stream(script, args)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Auto-select and run a chamber directory harvester")
    p.add_argument("url", help="Directory URL to scrape")
    p.add_argument("--out", required=True, help="Output CSV path")
    p.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    p.add_argument("--delay", type=float, default=0.6, help="Delay between actions/requests (seconds)")
    p.add_argument("--timeout-ms", type=int, default=60000, help="Playwright timeout in ms")
    p.add_argument("--max-pages", type=int, default=0, help="Max pages to paginate (0 = default in harvester)")
    p.add_argument("--probe-timeout-sec", type=int, default=180, help="Hard timeout for each probe subprocess")
    p.add_argument("--probe-parallel", type=int, default=2, help="Number of probes to run concurrently (1 = sequential)")
    p.add_argument(
        "--force",
        choices=[n for n, _ in CANDIDATES],
        help="Force a specific harvester and skip probing",
    )
    p.add_argument("--debug-probe-output", action="store_true", help="Print probe stderr/stdout for each harvester")
    return p


def main() -> int:
    args = build_parser().parse_args()
    try:
        require_safe_url(args.url, "directory URL")
    except ValueError as exc:
        log_error("validation", str(exc))
        return 2
    out_csv = Path(args.out).expanduser().resolve()

    # Validate scripts exist
    missing = [fname for _name, fname in CANDIDATES if not (HERE / fname).exists()]
    if missing:
        log_error("setup", f"Missing required scripts: {', '.join(missing)}")
        return 2

    lookup: Dict[str, Path] = {name: (HERE / fname) for name, fname in CANDIDATES}

    # If forced, skip probing
    if args.force:
        name = args.force
        script = lookup[name]
        extra: List[str] = []
        if name == "grid" and "/searchalpha/" in args.url.lower():
            extra.append("--alpha")
        if name == "atlas":
            extra.append("--enrich")
        print(f"Forced harvester: {name} -> {script.name}")
        return run_full(name, script, args.url, out_csv, args.headless, args.max_pages, args.delay, args.timeout_ms, extra_args=extra)

    ordered = CANDIDATES[:]
    if "chamberdata.net" in args.url.lower():
        ordered = [c for c in ordered if c[0] == "chamberdata"] + [c for c in ordered if c[0] != "chamberdata"]

    print(f"Probing harvesters (max {DEFAULT_PROBE_MAX_PAGES} pages each) to choose best match...")

    probe_jobs = []
    for name, fname in ordered:
        script = HERE / fname
        extra: List[str] = []
        if name == "grid":
            extra += ["--max-profiles", "30"]
            if "/searchalpha/" in args.url.lower():
                extra += ["--alpha"]
        if name == "atlas":
            extra += ["--max-categories", "40"]
        probe_jobs.append((name, script, extra))

    scores: Dict[str, int] = {}
    row_counts: Dict[str, int] = {}
    probe_out: Dict[str, str] = {}
    probe_stats: Dict[str, Dict[str, int]] = {}

    parallel = max(1, int(args.probe_parallel))
    if parallel == 1:
        for name, script, extra in probe_jobs:
            n, rows, quality, out, stats = run_probe(name, script, args.url, args.headless, args.delay, args.timeout_ms, args.probe_timeout_sec, extra_args=extra)
            row_counts[n] = rows
            scores[n] = quality
            probe_out[n] = out
            probe_stats[n] = stats
            print(f"  - {n:10s}: {rows} rows, quality {quality}, dup {stats.get("duplicates",0)}, bad names {stats.get("bad_names",0)}")
            if args.debug_probe_output and out.strip():
                print(out.strip())
    else:
        with ThreadPoolExecutor(max_workers=parallel) as ex:
            futs = {
                ex.submit(
                    run_probe,
                    name,
                    script,
                    args.url,
                    args.headless,
                    args.delay,
                    args.timeout_ms,
                    args.probe_timeout_sec,
                    extra,
                ): name
                for name, script, extra in probe_jobs
            }
            for fut in as_completed(futs):
                n, rows, quality, out, stats = fut.result()
                row_counts[n] = rows
                scores[n] = quality
                probe_out[n] = out
                probe_stats[n] = stats
                print(f"  - {n:10s}: {rows} rows, quality {quality}, dup {stats.get('duplicates',0)}, bad names {stats.get('bad_names',0)}")
                if args.debug_probe_output and out.strip():
                    print(out.strip())

    if not scores:
        print("No probe results available.")
        return 3

    # Choose best. If all zero, fail.
    if all(v <= 0 for v in scores.values()):
        print("\nNo harvester found rows during probe.")
        print("Try one of these:")
        print("  1) Run without --headless so you can see what loads")
        print("  2) Force a harvester: --force grid  (or cards / table / chamberdata / atlas)")
        print("  3) Increase timeout: --timeout-ms 90000   and/or --probe-timeout-sec 300")
        print("  4) Use --debug-probe-output to see probe failures")
        return 3

    best = max(scores.items(), key=lambda kv: kv[1])[0]
    best_rows = scores[best]

    script = lookup[best]
    extra: List[str] = []

    if best == "grid" and "/searchalpha/" in args.url.lower():
        extra.append("--alpha")

    if best == "atlas":
        extra.append("--enrich")

    print(f"\nSelected harvester: {best} -> {script.name} (probe rows: {best_rows})")
    print(f"Starting full run -> {out_csv}")

    return run_full(best, script, args.url, out_csv, args.headless, args.max_pages, args.delay, args.timeout_ms, extra_args=extra)


if __name__ == "__main__":
    raise SystemExit(main())
