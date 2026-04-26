@echo off
REM Chamber Outreach Harvester - Examples

REM One-time setup (run once):
REM   pip install -r requirements.txt
REM   python -m playwright install

REM Example 1: SD Chamber
python run_harvest.py "https://sdchamber.org/membership/directory-of-members/" --out sd.csv --headless --delay 0.6 --timeout-ms 60000

REM Example 2: Chula Vista
python run_harvest.py "https://web.chulavistachamber.org/2022/Chamber-Members" --out chula_vista.csv --headless --delay 0.8 --timeout-ms 60000

REM Example 3: Ramona (ChamberData)
python run_harvest.py "https://www.chamberdata.net/businesssearch.aspx?dbid2=caram" --out ramona.csv --headless --delay 0.6 --timeout-ms 60000

REM Example 4: East County Chamber (grid/tile directory)
python run_harvest.py "https://business.eastcountychamber.org/list/searchalpha/a" --out east_county.csv --headless --delay 0.8 --timeout-ms 60000
