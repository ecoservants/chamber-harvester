# Chamber Outreach Harvester — Intern Quickstart

These tools help EcoServants interns harvest **public Chamber of Commerce member directory listings** for outreach.
They open the directory in a real browser (Playwright), paginate through results and export a CSV.

## Files in this package

- `run_harvest.py` — **recommended**. Wrapper that auto-detects the directory layout by probing the harvesters and then runs the best one.
- `harvest_table_iframe.py` — best for **table-style** directories (columns like Company/Industry/Phone/Web).
- `harvest_cards_paged.py` — best for **card-style** directories (blocks with “Learn More” / “Visit Site”, numbered pages).
- `harvest_grid_directory.py` — best for **grid/tile directories** (ChamberMaster/GrowthZone style, clicks profiles).
- `harvest_chamberdata_az.py` — best for **chamberdata.net** (walks A–Z member directory pages via `dbid2`).

All harvesters:
- autosave continuously (writes the CSV after each page)
- are safe to interrupt (Ctrl+C saves what you have)

---

## One-time setup (Windows)

1) Install Python 3.10+ (if you already have Python, skip).
2) Open **Command Prompt** (or PowerShell) and install dependencies:

```bat
pip install -r requirements.txt
python -m playwright install
```

---

## Basic usage (recommended)

Run the wrapper and let it pick the best strategy:

```bat
python run_harvest.py "DIRECTORY_URL" --out output.csv --headless --delay 0.8 --timeout-ms 60000
```

### Examples

**San Diego Regional Chamber (table-style)**
```bat
python run_harvest.py "https://sdchamber.org/membership/directory-of-members/" --out sd.csv --headless --delay 0.6 --timeout-ms 60000
```

**Chula Vista Chamber (card-style)**
```bat
python run_harvest.py "https://web.chulavistachamber.org/2022/Chamber-Members" --out chula_vista.csv --headless --delay 0.8 --timeout-ms 60000
```

**Ramona (ChamberData)**
```bat
python run_harvest.py "https://www.chamberdata.net/businesssearch.aspx?dbid2=caram" --out ramona.csv --headless --delay 0.6 --timeout-ms 60000
```

---

## Big scrape settings

For large directories (hundreds or thousands of listings), use:
- `--headless` (faster, less UI)
- `--delay 0.6` to `1.2` (reduces blocking)
- `--timeout-ms 60000` to `90000`
- optionally raise `--max-pages` (default 5000)

Example:

```bat
python run_harvest.py "DIRECTORY_URL" --out big.csv --headless --delay 1.0 --timeout-ms 90000 --max-pages 5000
```

---

## Stopping safely

Press **Ctrl+C** any time.
The harvester will stop and your CSV will already include everything harvested so far.

---

## Troubleshooting

### 1) It says 0 rows but you see members in the browser
Run once **without** headless so you can see the page:

```bat
python run_harvest.py "DIRECTORY_URL" --out test.csv --delay 0.8 --timeout-ms 60000
```

Then try forcing a mode:

```bat
python run_harvest.py "DIRECTORY_URL" --out test.csv --headless --force cards
python run_harvest.py "DIRECTORY_URL" --out test.csv --headless --force table
python run_harvest.py "DIRECTORY_URL" --out test.csv --headless --force chamberdata
```

### 2) Playwright error / browsers not installed
Re-run:

```bat
python -m playwright install
```

### 3) “Access denied” / blocked
- Increase delay (try `--delay 1.2`)
- Reduce speed (don’t run multiple scrapes in parallel)
- Some sites may block automated browsing; stop and report to the team

---

## Responsible use rules (important)

- Only harvest **publicly visible** member directory data.
- Use a polite delay (`--delay`) and do not overload sites.
- Follow your team’s outreach policies (do-not-contact, unsubscribe handling).
- If a site’s Terms of Service prohibit scraping, stop and escalate to leadership.

---

## Output format

CSV columns vary slightly by strategy, but generally include:
- business name
- phone
- website
- address (best-effort on some layouts)
- profile link (when available)
- source directory URL



### Alpha (A–Z) directories (searchalpha)
If the directory uses `/list/searchalpha/<letter>`, the wrapper will automatically enable alpha traversal for grid directories.
You can also run the grid harvester directly with `--alpha`.
