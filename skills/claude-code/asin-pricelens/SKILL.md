---
name: asin-pricelens
description: ASIN PriceLens 价格透镜 — Batch-fetch Amazon ASIN prices across 17 marketplaces. Injects local delivery zip + currency cookies to get native local prices from any IP. Outputs HTML insight report + CSV. Use when the user asks for cross-market pricing intelligence, brand price segment analysis, or "check prices for these ASINs across multiple Amazon sites". AST-internal tool.
version: 1.1
---

# ASIN PriceLens 价格透镜

AST-internal tool for cross-marketplace Amazon price intelligence.

> One lens to see through 17 Amazon marketplaces' real local prices.

## Installation

```bash
git clone ssh://git.amazon.com:2222/pkg/PriceLens && cd PriceLens && pip install -e .
```

## When to activate

The user's request should match one of:
- Batch ASIN price lookup across ≥1 Amazon marketplaces
- Price band / brand distribution analysis
- Cross-market pricing comparison (e.g., "EU5 price spread for these ASINs")
- Competitive category pricing intelligence (with AST compliance framing)

## Invocation

Use the Bash tool to run the CLI:

```bash
pricelens \
  --markets DE,FR,IT,ES,UK,US \
  --input /path/to/asins.xlsx \
  --output /path/to/output_dir \
  --yes
```

Or with inline ASINs:
```bash
pricelens --markets DE,UK --asins B0DCBB2YTR,B09B96TG33 --output ./out --yes
```

### Optional parameters
- `--title "Report Title"` — customize HTML report title
- `--subtitle "2026.5.1 – 7.31"` — date range shown below title
- `--delay 1.0` — seconds between requests (default 0.4)
- `--workers 3` — parallel threads per market (default 6)

If `pricelens` is not on PATH, use `python -m pricelens.cli ...` instead.

The absolute path to the HTML report is printed on stdout's last line.

## Pre-flight reminder (mandatory)

Before running, always tell the user:
- Prices are what a local guest shopper sees at scrape time (not authoritative)
- Delivery address is injected per market (e.g. Berlin/DE, London/UK, NYC/US)
- Currency is forced to the market's native currency
- Tool is IP-independent — user's VPN state does not affect results
- AST-internal use only; strip attribution before sharing externally
- Recommend a 5–10 ASIN pilot before full-batch runs

## Input format

Accepts `.xlsx`, `.csv`, `.tsv`, `.txt`. Auto-detects columns:
- ASIN (required)
- Search Rank, Purchase Rank (optional)
- Keyword Searches / Search Volume (optional)
- Date-formatted columns (YYYY-MM) → volume time series

## Market codes

US, UK, DE, FR, IT, ES, NL, SE, PL, JP, CA, AU, AE, SA, SG, IN, MX, BR, TR

Common presets:
- EU5 = DE,FR,IT,ES,UK
- NA  = US,CA,MX
- APAC = JP,SG,IN,AU

## Output

Two files in the output directory (timestamped):
- `asin_detail_*.xlsx` — styled Excel detail (Segoe UI, colored header, frozen pane)
- `竞品ASIN分析报告_*.html` — interactive report:
  - Per-market tabs, KPI cards
  - Price Segments (3 equal-width tiers: Entry / Mid-tier / Premium)
  - Top Brands chart
  - Search Volume by ASIN (Top 30, horizontal bar)
  - Volume Trend line chart (if time-series data present)
  - Detail table with sort + filter per column

## Compliance rules (AST)

- Never share raw competitor pricing to clients — only anonymized aggregates
- Do NOT add DSP revenue and SA sales together (unrelated metrics)

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| `not_found` errors | ASIN not listed in that market | Expected behavior |
| High `unavailable` count | Anti-bot throttling | Retry with `--delay 1.5 --workers 3` |
| CLI not found on PATH | pip script dir not in PATH | Use `python -m pricelens.cli ...` |
