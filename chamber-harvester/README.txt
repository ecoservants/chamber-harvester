Chamber Harvesters (3 scripts)

1) harvest_table_iframe.py
   Best for table-style member directories (columns like Company/Industry/Phone/Web).
   Example:
     python harvest_table_iframe.py "https://sdchamber.org/membership/directory-of-members/" --out sd.csv --headless

2) harvest_cards_paged.py
   Best for card-style listings (blocks with Learn More / Visit Site, numbered pages).
   Example:
     python harvest_cards_paged.py "https://web.chulavistachamber.org/2022/Chamber-Members" --out chula.csv --headless

3) harvest_chamberdata_az.py
   Best for ChamberData directories. Provide dbid2 or a URL with dbid2.
   Example:
     python harvest_chamberdata_az.py "https://www.chamberdata.net/businesssearch.aspx?dbid2=caram" --out ramona.csv --headless
   It will visit A_memberdirectory.aspx ... Z_memberdirectory.aspx and merge results.

All scripts autosave after each page/letter and are Ctrl+C safe.


4) harvest_grid_directory.py
   Best for grid/tile directories (ChamberMaster/GrowthZone) that require clicking into profile pages.

5) run_harvest.py (NEW in v3.8)
   Wrapper that probes the harvesters and auto-selects the best match.

   Example:
     python run_harvest.py "https://sdchamber.org/membership/directory-of-members/" --out sd.csv --headless

   Useful flags:
     --force grid|cards|table|atlas|chamberdata   (skip probing)
     --probe-parallel 2                           (probe concurrently)
     --probe-timeout-sec 300                      (hard timeout per probe subprocess)
     --debug-probe-output                         (print probe stdout/stderr)

Notes:
- Probes are lightweight (max 3 pages) and temp probe CSVs are cleaned up automatically.
- Full runs stream output live so you can see progress.

