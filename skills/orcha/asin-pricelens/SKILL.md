---
name: asin-pricelens
description: ASIN PriceLens 价格透镜 — 批量抓取 Amazon 17 个站点的 ASIN 本地原生价格,自动注入本地邮编 + 币种 Cookie,生成 HTML 洞察报告(价格段卡片 × 柱形图 × 品牌均价 × 品牌气泡云 × Search Volume 交互图 × 可排序筛选明细表)+ Excel 明细。当用户请求跨站点价格对比、竞品 ASIN 价格情报、品类价盘调研时激活。与用户 VPN 状态无关。AST 内部工具。
version: 1.2
---

# ASIN PriceLens 价格透镜 · Cross-Market Amazon Pricing Intelligence

> 一个透镜,看穿 17 个 Amazon 站点的真实本地价格。

## Installation (for teammates)

```bash
git clone https://github.com/sissima95-pixel/PriceLens.git && cd PriceLens && pip install -e .
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
2. Calls Amazon's public `/portal-migration/hz/glow/address-change` endpoint to inject a local delivery address
3. Fetches `/dp/{ASIN}` with the local session → real native-currency price
4. Generates HTML report + Excel detail

**Key property:** Results are independent of the user's VPN state.

## Brand extraction strategy (v1.2.2)

Priority order (byline-first):
1. Byline anchor text ("Visit the X Store")
2. Store URL (/stores/BRAND/page/)
3. Store URL old style (/BRAND/b/ref=)
4. Product detail table (Brand: X)
5. JSON payload ("brand":"X")
6. Title first words (last resort only)

This prevents descriptive words (Portable, Wireless, etc.) from being mis-detected as brands.

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
pricelens --markets US --input /path/to/asins.xlsx --output /path/to/out --title "US Personal Fans" --subtitle "2026.5.1-7.31" --yes
```

### Pattern B — inline ASIN list
```bash
pricelens --markets DE,UK --asins B0DCBB2YTR,B09B96TG33 --output /path/to/out --yes
```

### Optional parameters
- `--title "Report Title"` — customize report title
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
- **All 19** → US,UK,DE,FR,IT,ES,NL,SE,PL,JP,CA,AU,AE,SA,SG,IN,MX,BR,TR

## Output

Two timestamped files in the output directory:
- `asin_detail_YYYYMMDD_HHMMSS.xlsx` — styled Excel (Segoe UI, Indigo header, alternating rows, frozen pane)
- `竞品ASIN分析报告_YYYYMMDD_HHMMSS.html` — interactive report:
  - Hero header (Indigo→Violet→Pink gradient)
  - Price Tier Cards (count, %, avg price per tier)
  - ASIN Count vertical bar chart (clickable → filters volume chart)
  - Brand Avg Price horizontal bar (Top 12, clickable)
  - Brand Bubble Cloud (Top 20, clickable)
  - Search Volume by ASIN (Top 15, dynamically filtered by price/brand clicks)
  - Detail table with sort + filter popups (Select All toggle)

## Price banding

- Always 3 tiers: Entry / Mid-tier / Premium
- Equal-width price spans across the full category range
- Users can override with custom bands via CLI prompt (e.g., "0-40, 40-80, 80+")

## Interactive features

- **Click price tier card or bar** → Volume chart shows only ASINs in that tier
- **Click brand bubble or brand avg bar** → Volume chart shows only that brand's ASINs
- **Click again** → Reset to full Top 15
- Filter label shows current selection `[ Entry ]` or `[ JISULIFE ]`

## Design system

- Palette: Indigo/Violet primary (#6366f1), 10-color chart cycle
- Font: Inter (Google Fonts), SF Mono for ASIN/prices
- Cards: 14px radius, light shadow, hover lift
- Background: #FAFAFA
- Table: gradient header, sticky, hover highlight

## Failure modes

| Symptom | Cause | Handling |
|---------|-------|----------|
| `not_found` | ASIN not in that market | Normal |
| `unavailable` | OOS at scrape time | Normal |
| All fail in one market | Throttling | Retry with `--delay 1.5 --workers 3` |

## Do NOT

- Do NOT call for single ASIN — use `fetch_external_page` instead
- Do NOT invoke without pre-flight reminder
- Do NOT share raw output externally without anonymization
