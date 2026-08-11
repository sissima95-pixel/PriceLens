# -*- coding: utf-8 -*-
"""ASIN PriceLens reporter — generates Excel and interactive HTML reports.

Clean rewrite 2026-08-07. UI style matched to AU RV Dashboard reference.
"""
from __future__ import annotations

import json
import html as html_mod
from pathlib import Path
from dataclasses import asdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .fetcher import PriceResult


# ===========================================================================
# Excel output
# ===========================================================================

def write_csv(results: list, path) -> None:
    """Write results to styled Excel file (.xlsx)."""
    path = Path(path)
    if path.suffix.lower() == ".csv":
        path = path.with_suffix(".xlsx")

    if not results:
        import openpyxl
        wb = openpyxl.Workbook()
        wb.active.append(["No results"])
        wb.save(path)
        return

    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    fieldnames = [
        "asin", "market", "currency", "price", "display_price",
        "title", "brand", "availability", "status", "url", "error",
        "search_rank", "purchase_rank", "search_volume",
    ]
    header_names = [
        "ASIN", "Market", "Currency", "Price", "Display Price",
        "Title", "Brand", "Availability", "Status", "URL", "Error",
        "Search Rank", "Purchase Rank", "Search Volume",
    ]
    series_keys: list[str] = []
    for r in results:
        d = asdict(r) if not isinstance(r, dict) else r
        vs = d.get("volume_series")
        if vs and isinstance(vs, dict):
            for k in vs:
                if k not in series_keys:
                    series_keys.append(k)
    series_keys.sort()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "ASIN Detail"

    header_font = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1E3A5F", end_color="1E3A5F", fill_type="solid")
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    body_font = Font(name="Segoe UI", size=10)
    body_align = Alignment(vertical="center", wrap_text=False)
    thin_border = Border(
        left=Side(style="thin", color="E2E8F0"),
        right=Side(style="thin", color="E2E8F0"),
        top=Side(style="thin", color="E2E8F0"),
        bottom=Side(style="thin", color="E2E8F0"),
    )

    headers = header_names + series_keys
    ws.append(headers)
    for col_idx, _ in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        cell.border = thin_border

    for r in results:
        d = asdict(r) if not isinstance(r, dict) else r
        row = [d.get(fn, "") for fn in fieldnames]
        vs = d.get("volume_series") or {}
        for sk in series_keys:
            row.append(vs.get(sk, ""))
        ws.append(row)

    alt_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    for row_idx in range(2, ws.max_row + 1):
        for col_idx in range(1, ws.max_column + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.font = body_font
            cell.alignment = body_align
            cell.border = thin_border
        if row_idx % 2 == 0:
            for col_idx in range(1, ws.max_column + 1):
                ws.cell(row=row_idx, column=col_idx).fill = alt_fill

    for col_idx in range(1, ws.max_column + 1):
        max_len = len(str(headers[col_idx - 1]))
        for row_idx in range(2, min(ws.max_row + 1, 20)):
            val = ws.cell(row=row_idx, column=col_idx).value
            if val:
                max_len = max(max_len, min(len(str(val)), 40))
        ws.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = max_len + 3

    ws.freeze_panes = "A2"
    wb.save(path)


# ===========================================================================
# HTML output
# ===========================================================================

_BAR_COLORS = ["#2563EB", "#F59E0B", "#16A34A", "#DC2626", "#7C3AED",
               "#0891B2", "#EA580C", "#4F46E5", "#059669", "#DB2777"]


def write_html(results: list, path, title: str = "ASIN Price Intelligence Report",
               subtitle: str = "") -> None:
    """Generate interactive HTML report matching professional dashboard style."""
    path = Path(path)
    if not results:
        path.write_text("<!DOCTYPE html><html><body><p>No results</p></body></html>",
                        encoding="utf-8")
        return

    rows = [asdict(r) if not isinstance(r, dict) else r for r in results]

    has_search_rank = any(r.get("search_rank") is not None for r in rows)
    has_purchase_rank = any(r.get("purchase_rank") is not None for r in rows)
    has_search_volume = any(r.get("search_volume") is not None for r in rows)
    has_volume_series = any(r.get("volume_series") for r in rows)

    markets_data: dict[str, list[dict]] = {}
    for r in rows:
        mk = r.get("market", "Unknown")
        markets_data.setdefault(mk, []).append(r)

    panels_html = ""
    tabs_html = ""
    first = True
    for mk, mrows in markets_data.items():
        active = " active" if first else ""
        tabs_html += f'<div class="tab{active}" data-market="{mk}">{mk} ({len(mrows)})</div>\n'
        panels_html += _render_market_panel(mk, mrows, active, has_search_rank,
                                            has_purchase_rank, has_search_volume,
                                            has_volume_series)
        first = False

    json_rows = [{k: v for k, v in r.items() if k != "volume_series"} for r in rows]
    volume_series_json = {}
    if has_volume_series:
        for r in rows:
            vs = r.get("volume_series")
            if vs:
                volume_series_json[r["asin"]] = vs

    escaped_title = html_mod.escape(title)
    escaped_subtitle = html_mod.escape(subtitle) if subtitle else ""
    html_content = _render_html(escaped_title, escaped_subtitle, tabs_html, panels_html,
                                json_rows, volume_series_json, has_search_rank,
                                has_purchase_rank, has_search_volume, has_volume_series)
    path.write_text(html_content, encoding="utf-8")


def _price_bands(prices: list[float]) -> list[tuple[str, int]]:
    """Price banding based on absolute price ranges (category-meaningful tiers).

    Always 3 tiers with equal-width price spans across the full range,
    so each tier covers the same dollar amount — reflects actual category
    price structure rather than quantile splits that over-segment the low end.
    """
    if not prices:
        return []
    sorted_p = sorted(prices)
    mn, mx = sorted_p[0], sorted_p[-1]
    n_bands = 3
    labels = ["Entry", "Mid-tier", "Premium"]

    # Equal-width: divide the full price range into 3 equal spans
    step = (mx - mn) / n_bands if mx > mn else max(mx * 0.1, 1)
    bounds = [mn + step * i for i in range(n_bands + 1)]
    # Ensure last bound captures max exactly
    bounds[-1] = mx

    bands = []
    for i in range(n_bands):
        lo, hi = bounds[i], bounds[i + 1]
        if i == n_bands - 1:
            count = sum(1 for p in prices if lo <= p <= hi)
        else:
            count = sum(1 for p in prices if lo <= p < hi)
        bands.append((f"{labels[i]}\n({lo:.0f}\u2013{hi:.0f})", count))
    return bands


def _summarize_market(mrows: list[dict]) -> dict:
    ok_rows = [r for r in mrows if r.get("status") == "ok" and r.get("price")]
    prices = [r["price"] for r in ok_rows]
    brands = set(r.get("brand", "") for r in ok_rows if r.get("brand"))
    return {
        "total": len(mrows),
        "ok": len(ok_rows),
        "unavailable": sum(1 for r in mrows if r.get("status") == "unavailable"),
        "not_found": sum(1 for r in mrows if r.get("status") == "not_found"),
        "error": sum(1 for r in mrows if r.get("status") == "error"),
        "min_price": min(prices) if prices else 0,
        "max_price": max(prices) if prices else 0,
        "avg_price": sum(prices) / len(prices) if prices else 0,
        "median_price": sorted(prices)[len(prices) // 2] if prices else 0,
        "brands_count": len(brands),
        "currency": ok_rows[0]["currency"] if ok_rows else "",
    }


def _fmt_vol(v: float) -> str:
    if v >= 1000:
        return f"{v/1000:.1f}k"
    return f"{v:.0f}"


def _render_market_panel(mk: str, mrows: list[dict], active: str,
                         has_sr: bool, has_pr: bool, has_sv: bool,
                         has_vs: bool) -> str:
    summary = _summarize_market(mrows)
    cur = summary["currency"]
    display = "block" if active else "none"

    # KPI row
    kpi_html = f'''
    <div class="kpi-row">
      <div class="kpi green"><div class="kpi-label">Priced Successfully</div><div class="kpi-val">{summary["ok"]}/{summary["total"]}</div></div>
      <div class="kpi"><div class="kpi-label">Min Price</div><div class="kpi-val">{cur} {summary["min_price"]:.2f}</div></div>
      <div class="kpi"><div class="kpi-label">Max Price</div><div class="kpi-val">{cur} {summary["max_price"]:.2f}</div></div>
      <div class="kpi"><div class="kpi-label">Median Price</div><div class="kpi-val">{cur} {summary["median_price"]:.2f}</div></div>
      <div class="kpi amber"><div class="kpi-label">Brands Detected</div><div class="kpi-val">{summary["brands_count"]}</div></div>
    </div>'''

    ok_rows = [r for r in mrows if r.get("status") == "ok" and r.get("price")]
    prices = [r["price"] for r in ok_rows]

    # Price bands
    bands = _price_bands(prices)
    band_html = ""
    if bands:
        max_count = max(c for _, c in bands) or 1
        band_html = '<div class="card"><div class="card-title">Price Segment Distribution</div>'
        for label, count in bands:
            pct = count / max_count * 100
            parts = label.split("\n")
            tier_name = html_mod.escape(parts[0])
            tier_range = html_mod.escape(parts[1]) if len(parts) > 1 else ""
            band_html += f'''<div class="hbar-row clickable-bar" data-filter-type="price" data-filter-value="{tier_name}" data-market="{mk}">
              <div class="hbar-label">{tier_name} <span class="hbar-sub">{tier_range}</span></div>
              <div class="hbar-track"><div class="hbar-fill" style="width:{pct:.1f}%;background:#2563EB"></div></div>
              <div class="hbar-val">{count}</div>
            </div>'''
        band_html += '</div>'

    # Brand distribution
    brand_counts: dict[str, int] = {}
    for r in ok_rows:
        b = r.get("brand", "").strip() or "Unknown"
        brand_counts[b] = brand_counts.get(b, 0) + 1
    top_brands = sorted(brand_counts.items(), key=lambda x: -x[1])[:10]
    brand_html = ""
    if top_brands:
        max_bc = top_brands[0][1] or 1
        brand_html = '<div class="card"><div class="card-title">Top Brands by ASIN Count</div>'
        for i, (bname, bcount) in enumerate(top_brands):
            pct = bcount / max_bc * 100
            color = _BAR_COLORS[i % len(_BAR_COLORS)]
            brand_html += f'''<div class="hbar-row clickable-bar" data-filter-type="brand" data-filter-value="{html_mod.escape(bname)}" data-market="{mk}">
              <div class="hbar-label">{html_mod.escape(bname)}</div>
              <div class="hbar-track"><div class="hbar-fill" style="width:{pct:.1f}%;background:{color}"></div></div>
              <div class="hbar-val">{bcount}</div>
            </div>'''
        brand_html += '</div>'

    # Search Volume by ASIN — JS-driven dynamic chart (filtered by price/brand clicks)
    vol_bar_html = ""
    if has_sv:
        vol_bar_html = f'<div class="section"><div class="section-title">Search Volume by ASIN (Top 15) <span class="vol-filter-label" id="vol-filter-{mk}"></span></div><div class="card"><div id="vol-chart-{mk}"></div></div></div>'

    # Volume trend
    volume_trend_html = ""
    if has_vs:
        volume_trend_html = f'<div class="section"><div class="section-title">Search Volume Trend</div><div class="card"><canvas id="vol-canvas-{mk}" height="180"></canvas></div></div>'

    # Detail table
    table_html = _render_detail_table(mk, mrows, has_sr, has_pr)

    return f'''
    <div class="tab-content{" active" if active else ""}" data-market="{mk}" style="display:{display}">
      <div class="section">
        <div class="section-title">Market Overview</div>
        {kpi_html}
        <div class="grid-2">{band_html}{brand_html}</div>
      </div>
      {vol_bar_html}
      {volume_trend_html}
      <div class="section">
        <div class="section-title">ASIN Detail</div>
        {table_html}
      </div>
    </div>'''


def _render_detail_table(mk: str, mrows: list[dict],
                         has_sr: bool, has_pr: bool) -> str:
    cols = ["ASIN", "Brand", "Title", "Price", "Status"]
    if has_sr:
        cols.append("Search Rank")
    if has_pr:
        cols.append("Purchase Rank")

    th_html = ""
    for i, c in enumerate(cols):
        th_html += f'<th data-col="{i}">{html_mod.escape(c)} <span class="th-sort" data-col="{i}">&#8597;</span> <span class="th-filter" data-col="{i}">&#9662;</span></th>'

    tbody_rows = ""
    for r in mrows:
        price_str = f'{r.get("currency","")} {r["price"]:.2f}' if r.get("price") else "-"
        status = r.get("status", "unknown")
        title_short = (r.get("title", "") or "")[:80]

        cells = [
            f'<a href="{html_mod.escape(r.get("url",""))}" target="_blank">{html_mod.escape(r.get("asin",""))}</a>',
            html_mod.escape(r.get("brand", "") or ""),
            f'<span class="dim">{html_mod.escape(title_short)}</span>',
            f'<td class="num">{price_str}</td>',
            f'<span class="st-{status}">{status}</span>',
        ]
        if has_sr:
            sv = r.get("search_rank")
            cells.append(f"{sv:.0f}" if sv is not None else "-")
        if has_pr:
            pv = r.get("purchase_rank")
            cells.append(f"{pv:.0f}" if pv is not None else "-")

        # Fix: price cell already wrapped in td
        td_parts = []
        for j, c in enumerate(cells):
            if c.startswith("<td"):
                td_parts.append(c)
            else:
                td_parts.append(f"<td>{c}</td>")
        tbody_rows += f'<tr>{"".join(td_parts)}</tr>\n'

    return f'''
      <div class="table-scroll">
        <table id="table-{mk}">
          <thead><tr>{th_html}</tr></thead>
          <tbody>{tbody_rows}</tbody>
        </table>
      </div>'''


def _render_html(title: str, subtitle: str, tabs_html: str, panels_html: str,
                 json_rows: list[dict], volume_series_json: dict,
                 has_sr: bool, has_pr: bool, has_sv: bool, has_vs: bool) -> str:
    row_json = json.dumps(json_rows, ensure_ascii=False, separators=(",", ":"))
    vol_json = json.dumps(volume_series_json, ensure_ascii=False, separators=(",", ":"))

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{font-family:'Segoe UI',system-ui,sans-serif;background:#F8FAFC;color:#1E293B;font-size:13px;}}
a{{color:#2563EB;text-decoration:none;}}
a:hover{{text-decoration:underline;}}

/* Header */
.header{{background:linear-gradient(135deg,#1E3A5F 0%,#2563EB 100%);color:#fff;padding:28px 40px;text-align:center;}}
.header h1{{font-size:22px;font-weight:700;letter-spacing:.3px;}}
.header .sub{{font-size:13px;opacity:.85;margin-top:4px;}}

/* Container */
.container{{max-width:1400px;margin:0 auto;padding:24px 32px;}}

/* Sections */
.section{{margin-bottom:32px;}}
.section-title{{font-size:15px;font-weight:700;color:#1E3A5F;border-left:4px solid #2563EB;padding-left:10px;margin-bottom:16px;}}

/* KPI */
.kpi-row{{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:20px;}}
.kpi{{background:#fff;border-radius:10px;padding:16px 20px;min-width:150px;flex:1;box-shadow:0 1px 4px rgba(0,0,0,.07);border-top:3px solid #2563EB;}}
.kpi.green{{border-top-color:#16A34A;}}
.kpi.amber{{border-top-color:#D97706;}}
.kpi-label{{font-size:11px;color:#64748B;text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px;}}
.kpi-val{{font-size:18px;font-weight:700;color:#1E293B;}}

/* Tabs */
.tabs{{display:flex;gap:4px;margin-bottom:0;border-bottom:2px solid #E2E8F0;}}
.tab{{padding:7px 16px;font-size:12px;font-weight:600;cursor:pointer;border-radius:6px 6px 0 0;color:#64748B;border:1px solid transparent;border-bottom:none;position:relative;bottom:-2px;transition:all .15s;}}
.tab.active{{background:#fff;color:#2563EB;border-color:#E2E8F0;border-bottom-color:#fff;}}
.tab:hover:not(.active){{background:#F8FAFC;color:#1E293B;}}
.tab-content{{display:none;}}
.tab-content.active{{display:block;padding-top:16px;}}

/* Cards & Grid */
.grid-2{{display:grid;grid-template-columns:1fr 1fr;gap:20px;}}
.card{{background:#fff;border-radius:10px;padding:20px;box-shadow:0 1px 4px rgba(0,0,0,.07);}}
.card-title{{font-size:12px;font-weight:700;color:#475569;text-transform:uppercase;letter-spacing:.5px;margin-bottom:14px;}}

/* Horizontal bars */
.hbar-row{{display:grid;grid-template-columns:140px 1fr 36px;align-items:center;gap:10px;margin-bottom:8px;}}
.hbar-row.hbar-vol{{grid-template-columns:95px 1fr;margin-bottom:10px;}}
.hbar-label{{font-size:12px;color:#334155;text-align:right;white-space:nowrap;}}
.hbar-mono{{font-family:'SF Mono','Consolas','Courier New',monospace;font-size:11px;color:#475569;}}
.hbar-sub{{color:#94A3B8;font-size:10px;margin-left:4px;}}
.hbar-track{{background:#F1F5F9;border-radius:4px;height:22px;display:flex;align-items:center;overflow:visible;position:relative;}}
.hbar-fill{{height:100%;border-radius:4px;min-width:2px;}}
.hbar-val{{font-size:11px;color:#64748B;font-weight:600;}}
.hbar-inline{{font-size:11px;color:#64748B;margin-left:8px;white-space:nowrap;}}
.clickable-bar{{cursor:pointer;border-radius:6px;padding:2px 4px;transition:background .15s;}}
.clickable-bar:hover{{background:#EFF6FF;}}
.clickable-bar.selected{{background:#DBEAFE;}}
.vol-filter-label{{font-size:12px;font-weight:400;color:#2563EB;margin-left:8px;}}

/* X-axis */
.vol-xaxis{{display:flex;justify-content:space-between;margin-top:8px;padding-left:105px;font-size:10px;color:#94A3B8;}}

/* Table */
.table-scroll{{max-height:2200px;overflow-y:auto;border-radius:10px;box-shadow:0 1px 4px rgba(0,0,0,.07);background:#fff;}}
table{{width:100%;border-collapse:collapse;font-size:12px;}}
th{{background:#F1F5F9;padding:8px 10px;text-align:left;font-weight:600;color:#475569;font-size:11px;border-bottom:2px solid #E2E8F0;position:sticky;top:0;z-index:10;white-space:nowrap;}}
td{{padding:7px 10px;border-bottom:1px solid #F1F5F9;vertical-align:middle;}}
td.num{{text-align:right;font-variant-numeric:tabular-nums;color:#334155;}}
tr:hover td{{background:#F8FAFC;}}
.dim{{color:#64748B;font-size:11px;}}

/* Sort / filter icons */
.th-sort,.th-filter{{color:#CBD5E1;cursor:pointer;font-size:11px;margin-left:2px;transition:color .15s;}}
.th-sort:hover,.th-filter:hover{{color:#2563EB;}}
.th-sort.active{{color:#2563EB;}}

/* Status */
.st-ok{{color:#16A34A;font-weight:600;}}
.st-unavailable{{color:#D97706;}}
.st-not_found{{color:#DC2626;}}
.st-error{{color:#DC2626;}}

/* Filter popup */
.filter-popup{{display:none;position:absolute;background:#fff;border:1px solid #E2E8F0;border-radius:10px;padding:14px;z-index:1000;min-width:210px;max-height:340px;overflow-y:auto;box-shadow:0 4px 20px rgba(0,0,0,.12);}}
.filter-popup.show{{display:block;}}
.fp-hint{{font-size:11px;color:#94A3B8;margin-bottom:8px;}}
.filter-popup label{{display:block;padding:3px 0;font-size:12px;color:#334155;cursor:pointer;}}
.filter-popup input[type="checkbox"]{{margin-right:6px;accent-color:#2563EB;}}
.filter-popup input[type="number"]{{width:80px;border:1px solid #E2E8F0;padding:4px 6px;border-radius:6px;font-size:12px;}}
.fp-actions{{margin-top:10px;display:flex;gap:8px;}}
.fp-btn{{padding:5px 14px;border-radius:6px;border:none;cursor:pointer;font-size:12px;font-weight:600;}}
.fp-apply{{background:#2563EB;color:#fff;}}
.fp-apply:hover{{background:#1D4ED8;}}
.fp-clear{{background:#F1F5F9;color:#475569;}}
.fp-clear:hover{{background:#E2E8F0;}}
.fp-selectall{{font-weight:700;padding-bottom:4px;border-bottom:1px solid #F1F5F9;margin-bottom:4px;}}

canvas{{width:100%!important;}}
</style>
</head>
<body>
<div class="header">
  <h1>{title}</h1>
  {'<div class="sub">' + subtitle + '</div>' if subtitle else ''}
</div>
<div class="container">
  <div class="tabs">{tabs_html}</div>
  {panels_html}
</div>
<div class="filter-popup" id="filterPopup"></div>

<script>
const rowData = {row_json};
const volumeSeries = {vol_json};
const HAS_VOLUME_SERIES = {"true" if has_vs else "false"};

// Tabs
document.querySelectorAll('.tab').forEach(t=>{{
  t.addEventListener('click',()=>{{
    document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(x=>{{x.classList.remove('active');x.style.display='none';}});
    t.classList.add('active');
    const mk=t.dataset.market;
    const panel=document.querySelector(`.tab-content[data-market="${{mk}}"]`);
    if(panel){{panel.classList.add('active');panel.style.display='block';}}
  }});
}});

// Sort
document.querySelectorAll('.th-sort').forEach(el=>{{
  el.addEventListener('click',e=>{{
    e.stopPropagation();
    const th=el.closest('th'),table=th.closest('table'),tbody=table.querySelector('tbody');
    const col=parseInt(el.dataset.col),rows=Array.from(tbody.querySelectorAll('tr'));
    const wasAsc=el.classList.contains('asc');
    table.querySelectorAll('.th-sort').forEach(s=>{{s.classList.remove('asc','desc','active');s.innerHTML='&#8597;';}});
    const asc=!wasAsc;
    el.classList.add(asc?'asc':'desc','active');
    el.innerHTML=asc?'&#9650;':'&#9660;';
    rows.sort((a,b)=>{{
      let va=a.cells[col]?.textContent.trim()||'',vb=b.cells[col]?.textContent.trim()||'';
      const na=parseFloat(va.replace(/[^\\d.\\-]/g,'')),nb=parseFloat(vb.replace(/[^\\d.\\-]/g,''));
      if(!isNaN(na)&&!isNaN(nb))return asc?na-nb:nb-na;
      return asc?va.localeCompare(vb):vb.localeCompare(va);
    }});
    rows.forEach(r=>tbody.appendChild(r));
  }});
}});

// Filter
const popup=document.getElementById('filterPopup');
let fCol=null,fTable=null;
document.querySelectorAll('.th-filter').forEach(el=>{{
  el.addEventListener('click',e=>{{
    e.stopPropagation();
    const th=el.closest('th'),table=th.closest('table'),col=parseInt(el.dataset.col);
    fCol=col;fTable=table;
    const rows=Array.from(table.querySelector('tbody').querySelectorAll('tr'));
    const vals=new Set();let isNum=true;
    rows.forEach(r=>{{const v=r.cells[col]?.textContent.trim()||'';vals.add(v);if(v&&v!=='-'&&isNaN(parseFloat(v.replace(/[^\\d.\\-]/g,''))))isNum=false;}});
    let h='';
    if(isNum&&vals.size>5){{
      h=`<div class="fp-hint">Numeric range</div>
        <label>Min: <input type="number" id="fMin" step="any"></label>
        <label style="margin-top:4px">Max: <input type="number" id="fMax" step="any"></label>
        <div class="fp-actions"><button class="fp-btn fp-apply" onclick="applyNum()">Apply</button><button class="fp-btn fp-clear" onclick="clearF()">Clear</button></div>`;
    }}else{{
      const sorted=Array.from(vals).sort();
      h=`<div class="fp-hint">Select values</div>`;
      h+=`<label class="fp-selectall"><input type="checkbox" id="fpSelectAll" checked onchange="toggleAll(this)"> <strong>Select All</strong></label>`;
      sorted.forEach(v=>{{h+=`<label><input type="checkbox" class="fp-item-cb" value="${{v.replace(/"/g,'&quot;')}}" checked> ${{v||'(empty)'}}</label>`;}});
      h+=`<div class="fp-actions"><button class="fp-btn fp-apply" onclick="applyTxt()">Apply</button><button class="fp-btn fp-clear" onclick="clearF()">Clear</button></div>`;
    }}
    popup.innerHTML=h;
    const rect=el.getBoundingClientRect();
    popup.style.top=(rect.bottom+window.scrollY+4)+'px';
    popup.style.left=Math.min(rect.left+window.scrollX,window.innerWidth-240)+'px';
    popup.classList.add('show');
  }});
}});
document.addEventListener('click',e=>{{if(!popup.contains(e.target)&&!e.target.classList.contains('th-filter'))popup.classList.remove('show');}});

function toggleAll(el){{popup.querySelectorAll('.fp-item-cb').forEach(cb=>cb.checked=el.checked);}}
function applyNum(){{
  const mn=parseFloat(document.getElementById('fMin').value),mx=parseFloat(document.getElementById('fMax').value);
  Array.from(fTable.querySelector('tbody').rows).forEach(r=>{{
    const v=parseFloat((r.cells[fCol]?.textContent||'').replace(/[^\\d.\\-]/g,''));
    let ok=true;if(!isNaN(mn)&&(isNaN(v)||v<mn))ok=false;if(!isNaN(mx)&&(isNaN(v)||v>mx))ok=false;
    r.style.display=ok?'':'none';
  }});
  popup.classList.remove('show');
}}
function applyTxt(){{
  const ck=new Set();popup.querySelectorAll('.fp-item-cb:checked').forEach(c=>ck.add(c.value));
  Array.from(fTable.querySelector('tbody').rows).forEach(r=>{{
    r.style.display=ck.has(r.cells[fCol]?.textContent.trim()||'')?'':'none';
  }});
  popup.classList.remove('show');
}}
function clearF(){{
  Array.from(fTable.querySelector('tbody').rows).forEach(r=>r.style.display='');
  popup.classList.remove('show');
}}

// === Dynamic Volume Chart (filtered by price/brand clicks) ===
const COLORS = ['#2563EB','#F59E0B','#16A34A','#DC2626','#7C3AED','#0891B2','#EA580C','#4F46E5','#059669','#DB2777','#2563EB','#F59E0B','#16A34A','#DC2626','#7C3AED'];
// Price tiers are dynamically computed from rowData per market
function computePriceTiers(mk){{
  const prices=rowData.filter(r=>r.market===mk&&r.price).map(r=>r.price);
  if(!prices.length)return[];
  const mn=Math.min(...prices),mx=Math.max(...prices);
  const step=(mx-mn)/3;
  return[
    {{name:'Entry',min:mn,max:mn+step}},
    {{name:'Mid-tier',min:mn+step,max:mn+step*2}},
    {{name:'Premium',min:mn+step*2,max:mx+1}}
  ];
}}

function getPriceTier(price, mk){{
  if(price===null||price===undefined)return null;
  const tiers=computePriceTiers(mk);
  for(const t of tiers){{if(price>=t.min&&price<t.max)return t.name;}}
  return tiers.length?tiers[tiers.length-1].name:null;
}}

function renderVolChart(mk, filterType, filterValue){{
  const container=document.getElementById('vol-chart-'+mk);
  const label=document.getElementById('vol-filter-'+mk);
  if(!container)return;
  let items=rowData.filter(r=>r.market===mk&&r.search_volume);
  if(filterType==='price'){{
    items=items.filter(r=>getPriceTier(r.price,mk)===filterValue);
    if(label)label.textContent='[ '+filterValue+' ]';
  }}else if(filterType==='brand'){{
    items=items.filter(r=>r.brand===filterValue);
    if(label)label.textContent='[ '+filterValue+' ]';
  }}else{{
    if(label)label.textContent='';
  }}
  items.sort((a,b)=>(b.search_volume||0)-(a.search_volume||0));
  items=items.slice(0,15);
  if(!items.length){{container.innerHTML='<div style=\"color:#94A3B8;padding:20px\">No data for this filter</div>';return;}}
  const maxV=items[0].search_volume||1;
  let html='';
  items.forEach((r,i)=>{{
    const pct=(r.search_volume/maxV*100).toFixed(1);
    const c=COLORS[i%COLORS.length];
    const brand=r.brand||'';
    html+=`<div class=\"hbar-row hbar-vol\"><div class=\"hbar-label hbar-mono\">${{r.asin}}</div><div class=\"hbar-track\"><div class=\"hbar-fill\" style=\"width:${{pct}}%;background:${{c}}\"></div><span class=\"hbar-inline\">${{brand}}</span></div></div>`;
  }});
  // X-axis
  html+='<div class=\"vol-xaxis\">';
  for(let i=0;i<=6;i++){{const v=maxV*i/6;html+=`<span>${{v>=1000?(v/1000).toFixed(1)+'k':Math.round(v)}}</span>`;}}
  html+='</div>';
  container.innerHTML=html;
}}

// Initial render for all markets
document.querySelectorAll('[id^=\"vol-chart-\"]').forEach(el=>{{
  const mk=el.id.replace('vol-chart-','');
  renderVolChart(mk,null,null);
}});

// Click handlers for price/brand bars
document.querySelectorAll('.clickable-bar').forEach(bar=>{{
  bar.addEventListener('click',()=>{{
    const mk=bar.dataset.market;
    const type=bar.dataset.filterType;
    const val=bar.dataset.filterValue;
    // Toggle selection
    const wasSelected=bar.classList.contains('selected');
    // Clear all selections in same market+type
    document.querySelectorAll(`.clickable-bar[data-market="${{mk}}"]`).forEach(b=>b.classList.remove('selected'));
    if(!wasSelected){{
      bar.classList.add('selected');
      renderVolChart(mk,type,val);
    }}else{{
      renderVolChart(mk,null,null);
    }}
  }});
}});

// Volume trend canvas
if(HAS_VOLUME_SERIES){{
  document.querySelectorAll('[id^="vol-canvas-"]').forEach(canvas=>{{
    const mk=canvas.id.replace('vol-canvas-','');
    const pr=rowData.filter(r=>r.market===mk);
    const dm={{}};
    pr.forEach(r=>{{const vs=volumeSeries[r.asin];if(vs)Object.entries(vs).forEach(([d,v])=>{{dm[d]=(dm[d]||0)+v;}});}});
    const dates=Object.keys(dm).sort();
    if(dates.length<2)return;
    const vals=dates.map(d=>dm[d]),maxV=Math.max(...vals)||1;
    const ctx=canvas.getContext('2d'),W=canvas.offsetWidth||600,H=170;
    canvas.width=W;canvas.height=H;const pad=44;
    ctx.strokeStyle='#E2E8F0';ctx.lineWidth=0.5;
    for(let i=0;i<=4;i++){{
      const y=pad+(H-2*pad)*(1-i/4);
      ctx.beginPath();ctx.moveTo(pad,y);ctx.lineTo(W-10,y);ctx.stroke();
      ctx.fillStyle='#94A3B8';ctx.font='10px Segoe UI,sans-serif';
      ctx.fillText(Math.round(maxV*i/4).toLocaleString(),2,y+3);
    }}
    ctx.strokeStyle='#2563EB';ctx.lineWidth=2.5;ctx.beginPath();
    dates.forEach((d,i)=>{{
      const x=pad+(W-pad-10)*i/(dates.length-1),y=pad+(H-2*pad)*(1-vals[i]/maxV);
      i===0?ctx.moveTo(x,y):ctx.lineTo(x,y);
    }});
    ctx.stroke();
    // Dots
    ctx.fillStyle='#2563EB';
    dates.forEach((d,i)=>{{
      const x=pad+(W-pad-10)*i/(dates.length-1),y=pad+(H-2*pad)*(1-vals[i]/maxV);
      ctx.beginPath();ctx.arc(x,y,3,0,Math.PI*2);ctx.fill();
    }});
    ctx.fillStyle='#64748B';ctx.font='10px Segoe UI,sans-serif';
    const step=Math.max(1,Math.floor(dates.length/6));
    dates.forEach((d,i)=>{{if(i%step===0||i===dates.length-1){{const x=pad+(W-pad-10)*i/(dates.length-1);ctx.fillText(d,x-15,H-4);}}}});
  }});
}}
</script>
</body>
</html>'''
