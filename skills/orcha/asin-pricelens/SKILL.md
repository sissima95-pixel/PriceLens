---
name: asin-pricelens
description: ASIN PriceLens 价格透镜 — 批量抓取 Amazon 17 个站点的 ASIN 本地原生价格,自动注入本地邮编 + 币种 Cookie,生成 HTML 洞察报告(品牌分布 × 价格段 × Search Volume 柱状图 × 可排序筛选明细表)+ CSV 明细。当用户请求跨站点价格对比、竞品 ASIN 价格情报、品类价盘调研时激活。与用户 VPN 状态无关。AST 内部工具。
version: 1.1
---

# ASIN PriceLens 价格透镜 · Cross-Market Amazon Pricing Intelligence

> 一个透镜,看穿 17 个 Amazon 站点的真实本地价格。

## Installation (for teammates)

```bash
git clone ssh://git.amazon.com:2222/pkg/PriceLens && cd PriceLens && pip install -e .
```

After install, the `pricelens` command is available system-wide.

## When to use this skill

Activate when the user requests any of:
- Batch ASIN price lookup across one or more Amazon marketplaces
- Cross-market pricing comparison ("查同一个 ASIN 在 EU5 的价格")
- Competitive category pricing intelligence
- Brand price segment analysis
- "Top-N median price" or "price band distribution" reports

## How it works

The `pricelens` CLI:
1. Opens per-marketplace HTTP session with pre-set delivery zipcode + currency cookie
2. Calls Amazon's public `/portal-migration/hz/glow/address-change` endpoint to inject a local delivery address (Berlin for DE, London for UK, NYC for US, ...)
3. Fetches `/dp/{ASIN}` with the local session → real native-currency price
4. Generates HTML report with KPI cards, price segments, brand distribution, Search Volume chart, sortable/filterable detail table

**Key property:** Results are independent of the user's VPN state. Works from any IP because delivery address is injected via cookie.

## Pre-flight — ALWAYS remind user BEFORE running

Before invoking the CLI, tell the user (in Chinese if session is Chinese):

```
🔍 ASIN PriceLens 使用前提醒:
• 抓取的是本地访客能看到的挂牌价,不是权威定价数据源
• 每个市场自动切换本地邮编(如 DE=柏林10115, US=NYC10001)
• 币种强制本地(EUR/GBP/USD/JPY/...)
• 与你 VPN 状态无关(cookie 注入,非 IP 判定)
• 仅限 AST 内部使用,分享给客户前需去除内部标注
• 建议先跑小批量(5-10 个 ASIN)验证再全量运行

预计耗时:
  ≤ 30 请求      →  1-2 分钟
  30-100 请求    →  3-8 分钟
  100-300 请求   →  15-40 分钟 (Amazon 限流)
  > 300 请求     →  分批或用 --delay 1.0 --workers 3 慢跑

输入文件如包含 "Search Rank" / "Purchase Rank" / "Keyword Searches" 列,会自动加入报告。
```

## Invocation

Use SHELL to invoke the CLI. Two patterns:

### Pattern A — from a CSV/Excel file
```bash
pricelens --markets DE,FR,IT,ES,UK,US --input /path/to/asins.xlsx --output /path/to/out --yes
```

### Pattern B — inline ASIN list
```bash
pricelens --markets DE,UK --asins B0DCBB2YTR,B09B96TG33 --output /path/to/out --yes
```

### Optional parameters
- `--title "Report Title"` — customize report title (default: "ASIN Price Intelligence Report")
- `--subtitle "2026.5.1 – 7.31"` — date range or context shown below title
- `--delay 1.0` — seconds between requests (use higher for large batches)
- `--workers 3` — parallel threads per market (lower = gentler on Amazon)

If `pricelens` is not on PATH, use `python -m pricelens.cli ...` instead.

The CLI prints the absolute path of the HTML report on stdout's last line.

## Market codes reference

| Code | Marketplace | Currency |
|------|-------------|----------|
| US | amazon.com | USD |
| UK | amazon.co.uk | GBP |
| DE | amazon.de | EUR |
| FR | amazon.fr | EUR |
| IT | amazon.it | EUR |
| ES | amazon.es | EUR |
| NL | amazon.nl | EUR |
| SE | amazon.se | SEK |
| PL | amazon.pl | PLN |
| JP | amazon.co.jp | JPY |
| CA | amazon.ca | CAD |
| AU | amazon.com.au | AUD |
| AE | amazon.ae | AED |
| SA | amazon.sa | SAR |
| SG | amazon.sg | SGD |
| IN | amazon.in | INR |
| MX | amazon.com.mx | MXN |
| BR | amazon.com.br | BRL |
| TR | amazon.com.tr | TRY |

## Common presets

- **EU5** → DE,FR,IT,ES,UK
- **NA** → US,CA,MX
- **APAC** → JP,SG,IN,AU
- **All Europe** → DE,FR,IT,ES,UK,NL,SE,PL
- **All 19** → US,UK,DE,FR,IT,ES,NL,SE,PL,JP,CA,AU,AE,SA,SG,IN,MX,BR,TR

## Input format

Accepts `.xlsx`, `.csv`, `.tsv`, or `.txt` files. Auto-detects optional columns:
- **ASIN** (required) — 10-char alphanumeric
- **Search Rank** — numeric rank from keyword tools
- **Purchase Rank** — numeric rank from keyword tools
- **Keyword Searches / Search Volume** — single snapshot number
- **Date columns** (YYYY-MM format headers) — treated as volume time series

## Output

Two timestamped files in the output directory:
- `asin_prices_YYYYMMDD_HHMMSS.csv` — raw detail, one row per (ASIN × market)
- `asin_prices_YYYYMMDD_HHMMSS.html` — interactive report:
  - Per-market tabs
  - KPI cards (priced count, min/max/median price, brands)
  - Price Segments chart (adaptive 3 or 4 tiers)
  - Top Brands horizontal bar chart
  - Search Volume by ASIN (Top 30, horizontal bar, color-coded)
  - Volume Trend line chart (if time-series data provided)
  - Detail table with per-column sort + filter popups

## Smart price banding

- Price spread < 3× → 3 tiers (Entry / Mid-tier / Premium)
- Price spread > 5× AND n ≥ 20 → 4 tiers (Entry / Mainstream / Premium / Flagship)
- Boundaries use quantile splits for n ≥ 12, equal-width for smaller samples

## Failure modes

| Symptom | Cause | Handling |
|---------|-------|----------|
| `not_found` status | ASIN not listed in that market | Normal, tell user |
| `unavailable` status | Genuinely OOS at scrape time | Normal, tell user |
| All rows fail in one market | Anti-bot throttling | Retry with `--delay 1.5 --workers 3` |
| Empty brand column | Non-standard byline HTML | Cosmetic only, price still accurate |

## Client-safe output preparation

When user asks for a client-shareable version:
1. The HTML has no internal attribution text to strip (clean by default)
2. Use anonymized Peer Benchmarking framing, not raw competitor pricing (per AST compliance)

## Do NOT

- Do NOT call this skill for a single ASIN lookup — inline `fetch_external_page` is enough
- Do NOT invoke without pre-flight reminder
- Do NOT use output naming specific competitors in client-facing materials
