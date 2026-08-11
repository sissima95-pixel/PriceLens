---
name: asin-pricelens
description: ASIN PriceLens 价格透镜 — batch fetch Amazon ASIN prices across 17 marketplaces with cookie-based geo-fencing bypass. Generates interactive HTML report + Excel detail.
version: 1.2
agent: claude-code
---

# ASIN PriceLens — CLI Usage for Claude Code

## Install
```bash
git clone https://github.com/sissima95-pixel/PriceLens.git && cd PriceLens && pip install -e .
```

## Quick usage
```bash
# From file
pricelens --markets US,DE --input asins.xlsx --output ./out --title "Category Report" --subtitle "2026.5-7" --yes

# Inline ASINs
pricelens --markets AU --asins B0DCBB2YTR,B09B96TG33 --output ./out --yes
```

## Key flags
- `--markets` — comma-separated: US,UK,DE,FR,IT,ES,NL,SE,PL,JP,CA,AU,AE,SA,SG,IN,MX,BR,TR
- `--input` — .xlsx/.csv/.txt file with ASIN column (auto-detects Search Rank, Purchase Rank, Keyword Searches)
- `--delay 1.0 --workers 3` — for large batches (>100 ASINs)
- `--title` / `--subtitle` — report header text

## Output
- `asin_detail_*.xlsx` — styled Excel
- `竞品ASIN分析报告_*.html` — interactive report with:
  - Price tier cards + vertical bar (clickable)
  - Brand avg price chart (clickable)
  - Brand bubble cloud (clickable)
  - Search Volume Top 15 (dynamically filtered)
  - Sortable/filterable detail table

## Brand extraction (v1.2.2)
Byline-first strategy: storefront anchor → store URL → product table → JSON → title (last resort).

## Design
Indigo/Violet palette, Inter font, Hero gradient, card-based layout.
