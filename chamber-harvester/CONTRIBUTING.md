# Contributing

- Keep intern safety first. New navigation paths should use `safe_goto()` or `require_safe_url()`.
- Keep shared parsing, scoring and URL logic in `harvest_common.py`.
- Avoid hardcoded chamber-specific domains unless clearly documented as examples.
- Do not commit scraped CSVs, logs, local output files or cache folders.

Before opening a pull request, run:

```bash
python -m compileall .
```
