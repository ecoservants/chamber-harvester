# Security Notes

This suite is intended for interns running local harvesters against public chamber directory pages.

Implemented safeguards:

- Browser navigation is validated through `harvest_common.safe_goto()`.
- URL normalization rejects unsafe schemes such as `file:`, `javascript:`, `data:` and `vbscript:`.
- Local/private targets are blocked, including localhost, `.local`, loopback IPs, private IPs, link-local IPs and unspecified addresses.
- Dependencies are pinned in `requirements.txt`.

Use this only on public directory data where collection is appropriate. Respect website terms, rate limits and privacy expectations.
