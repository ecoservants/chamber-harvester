# Graph Report - chamber-harvester  (2026-05-01)

## Corpus Check
- 7 files · ~7,990 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 96 nodes · 221 edges · 7 communities detected
- Extraction: 83% EXTRACTED · 17% INFERRED · 0% AMBIGUOUS · INFERRED: 38 edges (avg confidence: 0.8)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]

## God Nodes (most connected - your core abstractions)
1. `enrich_member()` - 11 edges
2. `safe_goto()` - 11 edges
3. `extract_cards()` - 10 edges
4. `normalize_url()` - 10 edges
5. `row_key()` - 10 edges
6. `main()` - 9 edges
7. `scrape()` - 9 edges
8. `scrape()` - 9 edges
9. `extract_contact_from_profile()` - 8 edges
10. `scrape()` - 8 edges

## Surprising Connections (you probably didn't know these)
- `extract_contact_from_profile()` --calls--> `normalize_url()`  [INFERRED]
  harvest_atlas_directory.py → harvest_common.py
- `extract_contact_from_profile()` --calls--> `choose_best_website()`  [INFERRED]
  harvest_atlas_directory.py → harvest_common.py
- `extract_contact_from_profile()` --calls--> `maybe_blank_chamber_email()`  [INFERRED]
  harvest_atlas_directory.py → harvest_common.py
- `enrich_rows()` --calls--> `clean_address()`  [INFERRED]
  harvest_atlas_directory.py → harvest_common.py
- `enrich_rows()` --calls--> `host_of()`  [INFERRED]
  harvest_atlas_directory.py → harvest_common.py

## Communities

### Community 0 - "Community 0"
Cohesion: 0.24
Nodes (19): choose_best_website(), clean_address(), clean_text(), domain_of_email(), host_of(), is_safe_url(), is_suspicious_name(), load_csv_quality() (+11 more)

### Community 1 - "Community 1"
Cohesion: 0.28
Nodes (15): clean(), click_next(), discover_alpha_urls(), extract_profile_links(), looks_like_profile_href(), main(), Member, norm_url() (+7 more)

### Community 2 - "Community 2"
Cohesion: 0.26
Nodes (14): collect_category_urls(), enrich_rows(), extract_contact_from_profile(), guess_all_categories_url(), main(), norm(), Collect /atlas/directory/category/* URLs on the page., Return (email, website) best-effort. (+6 more)

### Community 3 - "Community 3"
Cohesion: 0.35
Nodes (11): clean(), click_next(), find_best_table(), main(), norm_url(), pick_best_context(), Row, row_from_table() (+3 more)

### Community 4 - "Community 4"
Cohesion: 0.24
Nodes (11): build_parser(), count_csv_rows(), main(), Return (name, rows, quality_score, combined_output, stats) for a quick probe., Return number of data rows (excluding header)., Run a harvester, capturing stdout/stderr., Run a harvester, streaming stdout/stderr to the console., run_full() (+3 more)

### Community 5 - "Community 5"
Cohesion: 0.35
Nodes (10): Card, clean(), click_next_or_number(), extract_cards(), main(), norm_url(), pick_best_context(), score_card_html() (+2 more)

### Community 6 - "Community 6"
Cohesion: 0.42
Nodes (9): clean(), collect_member_links(), enrich_member(), guess_letter_urls(), infer_dbid2(), main(), Member, scrape() (+1 more)

## Knowledge Gaps
- **8 isolated node(s):** `Return (email, website) best-effort.`, `Collect /atlas/directory/category/* URLs on the page.`, `Validate URLs before local-browser navigation.`, `Discover A–Z alpha directory links from the current page.      Strategy:`, `Return number of data rows (excluding header).` (+3 more)
  These have ≤1 connection - possible missing edges or undocumented components.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `safe_goto()` connect `Community 2` to `Community 0`, `Community 1`, `Community 3`, `Community 5`, `Community 6`?**
  _High betweenness centrality (0.451) - this node is a cross-community bridge._
- **Why does `scrape()` connect `Community 3` to `Community 2`?**
  _High betweenness centrality (0.160) - this node is a cross-community bridge._
- **Why does `require_safe_url()` connect `Community 0` to `Community 2`, `Community 4`?**
  _High betweenness centrality (0.133) - this node is a cross-community bridge._
- **Are the 7 inferred relationships involving `enrich_member()` (e.g. with `safe_goto()` and `host_of()`) actually correct?**
  _`enrich_member()` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `safe_goto()` (e.g. with `scrape_category_page()` and `enrich_rows()`) actually correct?**
  _`safe_goto()` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Are the 5 inferred relationships involving `extract_cards()` (e.g. with `host_of()` and `choose_best_website()`) actually correct?**
  _`extract_cards()` has 5 INFERRED edges - model-reasoned connections that need verification._
- **Are the 6 inferred relationships involving `normalize_url()` (e.g. with `extract_contact_from_profile()` and `norm_url()`) actually correct?**
  _`normalize_url()` has 6 INFERRED edges - model-reasoned connections that need verification._