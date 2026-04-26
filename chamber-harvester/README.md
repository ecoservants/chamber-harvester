# EcoServants Chamber Outreach Harvester Suite

Browser-based harvesters for public chamber of commerce member directories. The suite supports several common directory layouts and can auto-probe a target URL to select the best harvester.

## Purpose

This tool helps EcoServants collect public business/member directory data for outreach workflows such as:

**Claim → Harvest → Upload → Confirm**

It is intended for public directory pages only. Do not use it to bypass logins, scrape private data or ignore website terms.

## Included harvesters

- `harvest_table_iframe.py` — table and iframe-based directories
- `harvest_cards_paged.py` — card/listing directories with pagination
- `harvest_grid_directory.py` — grid/tile directories, including optional A-Z traversal
- `harvest_atlas_directory.py` — Atlas/GrowthZone-style category directories
- `harvest_chamberdata_az.py` — ChamberData A-Z directories
- `run_harvest.py` — auto-probes and runs the best matching harvester

## Security posture

This GitHub-ready version includes local-system safeguards for intern use:

- Blocks unsafe schemes before browser navigation: `file://`, `javascript:`, `data:`, `vbscript:` and similar
- Blocks localhost and private/local IP targets
- Centralizes URL cleanup and validation in `harvest_common.py`
- Uses `domcontentloaded` instead of `networkidle` to reduce hangs on analytics/live widgets
- Pins dependencies for reproducible installs

See `SECURITY.md` for details.

## Installation

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
python -m playwright install chromium
```

## Basic usage

Auto-select a harvester:

```bash
python run_harvest.py "https://examplechamber.org/member-directory" --out members.csv --headless
```

Force a specific harvester:

```bash
python run_harvest.py "https://examplechamber.org/member-directory" --out members.csv --headless --force grid
```

Atlas/GrowthZone example:

```bash
python harvest_atlas_directory.py "https://web.example.org/atlas/directory/all-categories" --out atlas_members.csv --headless --enrich
```

ChamberData example:

```bash
python harvest_chamberdata_az.py "your_dbid2_value" --out chamberdata_members.csv --headless
```

## Output columns

Columns vary slightly by harvester but commonly include:

- `name`
- `phone`
- `email`
- `website`
- `address`
- `profile_url`
- `source_url`
- category/industry/letter fields when available

## Recommended next improvements

1. Add tests for URL normalization, scoring, CSV output and job recovery.
2. Continue consolidating duplicated logic into `harvest_common.py`.
3. Replace remaining broad exception handling with specific logged failures.
4. Move toward a shared base harvester or registry pattern.
5. Improve CSV writing for very large runs by writing once at the end or appending safely.
