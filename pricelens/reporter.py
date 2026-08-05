# -*- coding: utf-8 -*-
"""ASIN PriceLens reporter — generates CSV and interactive HTML reports.

Clean rewrite 2026-08-05.
"""
from __future__ import annotations

import csv
import json
import html as html_mod
from pathlib import Path
from dataclasses import asdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .fetcher import PriceResult


# ===========================================================================
# CSV output
# ===========================================================================

def write_csv(results: list, path) -> None:
    """Write results to CSV with all available fields."""
    path = Path(path)
    if not results:
        path.write_text("No results\n", encoding="utf-8")
        return

    fieldnames = [
        "asin", "market", "currency", "price", "display_price",
        "title", "brand", "availability", "status", "url", "error",
        "search_rank", "purchase_rank", "search_volume",
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

    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(fieldnames + series_keys)
        for r in results:
            d = asdict(r) if not isinstance(r, dict) else r
            row = [d.get(fn, "") for fn in fieldnames]
            vs = d.get("volume_series") or {}
            for sk in series_keys:
                row.append(vs.get(sk, ""))
            writer.writerow(row)


# ===========================================================================
# HTML output
# ===========================================================================

# Color palette for volume chart bars (cycling)
_BAR_COLORS = ["#2196F3", "#FF9800", "#4CAF50", "#F44336", "#2196F3",
               "#9C27B0", "#00BCD4", "#FF5722", "#8BC34A", "#3F51B5"]


def write_html(results: list, path, title: str = "ASIN Price Intelligence Report",
               subtitle: str = "") -> None:
    """Generate interactive HTML report.

    Args:
        subtitle: optional line below title, e.g. date range "2026.5.1 – 7.31"
    """
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
        tabs_html += f'<button class="tab-btn{active}" data-market="{mk}">{mk} ({len(mrows)})</button>\n'
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
    """Smart adaptive price banding."""
    if not prices:
        return []
    sorted_p = sorted(prices)
    mn, mx = sorted_p[0], sorted_p[-1]
    n = len(prices)
    ratio = 999 if mn <= 0 else mx / mn
    n_bands = 4 if (ratio > 5.0 and n >= 20) else 3

    if n >= 12:
        if n_bands == 3:
            bounds = [sorted_p[0], sorted_p[n // 3], sorted_p[2 * n // 3], sorted_p[-1]]
            labels = ["Entry", "Mid-tier", "Premium"]
        else:
            bounds = [sorted_p[0], sorted_p[n // 4], sorted_p[n // 2],
                      sorted_p[3 * n // 4], sorted_p[-1]]
            labels = ["Entry", "Mainstream", "Premium", "Flagship"]
    else:
        step = (mx - mn) / n_bands if mx > mn else max(mx * 0.1, 1)
        bounds = [mn + step * i for i in range(n_bands + 1)]
        labels = (["Entry", "Mid-tier", "Premium"] if n_bands == 3
                  else ["Entry", "Mainstream", "Premium", "Flagship"])

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
    """Format volume number: 5878 -> '5.9k'"""
    if v >= 1000:
        return f"{v/1000:.1f}k"
    return f"{v:.0f}"


def _render_market_panel(mk: str, mrows: list[dict], active: str,
                         has_sr: bool, has_pr: bool, has_sv: bool,
                         has_vs: bool) -> str:
    summary = _summarize_market(mrows)
    cur = summary["currency"]
    display = "block" if active else "none"

    # KPI
    kpi_html = f'''
    <div class="kpi-row">
      <div class="kpi-card"><div class="kpi-value">{summary["ok"]}<span class="kpi-sub">/{summary["total"]}</span></div><div class="kpi-label">Priced</div></div>
      <div class="kpi-card"><div class="kpi-value">{cur} {summary["min_price"]:.2f}</div><div class="kpi-label">Min Price</div></div>
      <div class="kpi-card"><div class="kpi-value">{cur} {summary["max_price"]:.2f}</div><div class="kpi-label">Max Price</div></div>
      <div class="kpi-card"><div class="kpi-value">{cur} {summary["median_price"]:.2f}</div><div class="kpi-label">Median</div></div>
      <div class="kpi-card"><div class="kpi-value">{summary["brands_count"]}</div><div class="kpi-label">Brands</div></div>
    </div>'''

    ok_rows = [r for r in mrows if r.get("status") == "ok" and r.get("price")]
    prices = [r["price"] for r in ok_rows]

    # Price bands (horizontal bar)
    bands = _price_bands(prices)
    band_html = ""
    if bands:
        max_count = max(c for _, c in bands) or 1
        band_html = '<div class="chart-card"><div class="chart-title">Price Segments</div>'
        for label, count in bands:
            pct = count / max_count * 100
            parts = label.split("\n")
            tier_name = html_mod.escape(parts[0])
            tier_range = html_mod.escape(parts[1]) if len(parts) > 1 else ""
            band_html += f'''<div class="hbar-row">
              <div class="hbar-label">{tier_name} <span class="hbar-sub">{tier_range}</span></div>
              <div class="hbar-track"><div class="hbar-fill" style="width:{pct:.1f}%;background:#2196F3"></div></div>
              <div class="hbar-val">{count}</div>
            </div>'''
        band_html += '</div>'

    # Brand distribution (horizontal bar)
    brand_counts: dict[str, int] = {}
    for r in ok_rows:
        b = r.get("brand", "").strip() or "Unknown"
        brand_counts[b] = brand_counts.get(b, 0) + 1
    top_brands = sorted(brand_counts.items(), key=lambda x: -x[1])[:10]
    brand_html = ""
    if top_brands:
        max_bc = top_brands[0][1] or 1
        brand_html = '<div class="chart-card"><div class="chart-title">Top Brands</div>'
        for i, (bname, bcount) in enumerate(top_brands):
            pct = bcount / max_bc * 100
            color = _BAR_COLORS[i % len(_BAR_COLORS)]
            brand_html += f'''<div class="hbar-row">
              <div class="hbar-label">{html_mod.escape(bname)}</div>
              <div class="hbar-track"><div class="hbar-fill" style="width:{pct:.1f}%;background:{color}"></div></div>
              <div class="hbar-val">{bcount}</div>
            </div>'''
        brand_html += '</div>'

    # Search Volume by ASIN (Top 30) — horizontal bar chart like the reference
    vol_bar_html = ""
    if has_sv:
        vol_items = [(r.get("asin", ""), r.get("brand", ""), r.get("search_volume", 0) or 0)
                     for r in mrows if r.get("search_volume")]
        vol_items.sort(key=lambda x: -x[2])
        vol_items = vol_items[:30]
        if vol_items:
            max_vol = vol_items[0][2] or 1
            vol_bar_html = '<div class="chart-card chart-full"><div class="chart-title">\U0001f4ca Search Volume by ASIN (Top 30, sorted descending)</div>'
            for i, (asin, brand, vol) in enumerate(vol_items):
                pct = vol / max_vol * 100
                color = _BAR_COLORS[i % len(_BAR_COLORS)]
                brand_label = html_mod.escape(brand) if brand else ""
                vol_bar_html += f'''<div class="hbar-row hbar-vol">
                  <div class="hbar-label hbar-label-mono">{html_mod.escape(asin)}</div>
                  <div class="hbar-track"><div class="hbar-fill" style="width:{pct:.1f}%;background:{color}"></div><span class="hbar-inline-val">{brand_label}</span></div>
                </div>'''
            # X-axis labels
            vol_bar_html += '<div class="vol-xaxis">'
            steps = 6
            for i in range(steps + 1):
                val = max_vol * i / steps
                vol_bar_html += f'<span>{_fmt_vol(val)}</span>'
            vol_bar_html += '</div>'
            vol_bar_html += '</div>'

    # Volume trend (canvas)
    volume_trend_html = ""
    if has_vs:
        volume_trend_html = f'<div class="chart-card chart-full"><div class="chart-title">Search Volume Trend</div><canvas id="vol-canvas-{mk}" height="180"></canvas></div>'

    # Detail table
    table_html = _render_detail_table(mk, mrows, has_sr, has_pr)

    return f'''
    <div class="market-panel" data-market="{mk}" style="display:{display}">
      {kpi_html}
      <div class="charts-grid">{band_html}{brand_html}</div>
      {vol_bar_html}
      {volume_trend_html}
      {table_html}
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
        th_html += f'<th data-col="{i}">{html_mod.escape(c)} <span class="th-sort" data-col="{i}">&#8597;</span><span class="th-filter" data-col="{i}">&#9662;</span></th>'

    tbody_rows = ""
    for r in mrows:
        price_str = f'{r.get("currency","")} {r["price"]:.2f}' if r.get("price") else "-"
        status = r.get("status", "unknown")
        title_short = (r.get("title", "") or "")[:80]

        cells = [
            f'<a href="{html_mod.escape(r.get("url",""))}" target="_blank" class="asin-link">{html_mod.escape(r.get("asin",""))}</a>',
            html_mod.escape(r.get("brand", "") or ""),
            f'<span class="title-cell">{html_mod.escape(title_short)}</span>',
            f'<span class="price-cell">{price_str}</span>',
            f'<span class="st-{status}">{status}</span>',
        ]
        if has_sr:
            sv = r.get("search_rank")
            cells.append(f"{sv:.0f}" if sv is not None else "-")
        if has_pr:
            pv = r.get("purchase_rank")
            cells.append(f"{pv:.0f}" if pv is not None else "-")

        td_html = "".join(f"<td>{c}</td>" for c in cells)
        tbody_rows += f'<tr>{td_html}</tr>\n'

    return f'''
    <div class="table-section">
      <div class="table-title">Detail &mdash; {len(mrows)} ASINs</div>
      <table class="detail-table" id="table-{mk}">
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
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: #f5f6fa;
  color: #333;
  line-height: 1.5;
}}
a {{ color: #1a73e8; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}

/* Header */
.header {{
  background: #fff;
  border-bottom: 1px solid #e8e8e8;
  padding: 24px 40px;
  text-align: center;
}}
.header h1 {{ font-size: 1.4rem; font-weight: 600; color: #222; }}
.header .sub {{ color: #999; font-size: 0.8rem; margin-top: 4px; }}

/* Layout */
.container {{ max-width: 1500px; margin: 0 auto; padding: 24px 32px; }}

/* Tabs */
.tabs {{ display: flex; gap: 6px; margin-bottom: 24px; flex-wrap: wrap; }}
.tab-btn {{
  background: #fff; border: 1px solid #ddd; color: #666;
  padding: 6px 16px; border-radius: 18px; cursor: pointer;
  font-size: 0.84rem; font-weight: 500; transition: all 0.15s;
}}
.tab-btn:hover {{ background: #f0f0f0; color: #333; }}
.tab-btn.active {{ background: #1a73e8; border-color: #1a73e8; color: #fff; }}

/* KPI */
.kpi-row {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px,1fr)); gap: 12px; margin-bottom: 24px; }}
.kpi-card {{
  background: #fff; border: 1px solid #eee; border-radius: 8px;
  padding: 16px 12px; text-align: center;
}}
.kpi-value {{ font-size: 1.3rem; font-weight: 700; color: #222; }}
.kpi-value .kpi-sub {{ font-size: 0.85rem; color: #aaa; font-weight: 400; }}
.kpi-label {{ font-size: 0.7rem; color: #999; margin-top: 3px; text-transform: uppercase; letter-spacing: 0.3px; }}

/* Charts */
.charts-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px,1fr)); gap: 20px; margin-bottom: 20px; }}
.chart-card {{
  background: #fff; border: 1px solid #eee; border-radius: 8px; padding: 20px 24px;
}}
.chart-card.chart-full {{ margin-bottom: 20px; }}
.chart-title {{ font-size: 0.88rem; font-weight: 600; color: #444; margin-bottom: 16px; }}

/* Horizontal bar rows */
.hbar-row {{ display: grid; grid-template-columns: 140px 1fr 40px; align-items: center; gap: 10px; margin-bottom: 8px; }}
.hbar-row.hbar-vol {{ grid-template-columns: 90px 1fr; margin-bottom: 12px; }}
.hbar-label {{ font-size: 0.78rem; color: #555; text-align: right; white-space: normal; word-break: keep-all; }}
.hbar-label-mono {{ font-family: 'SF Mono','Consolas',monospace; font-size: 0.75rem; color: #666; }}
.hbar-sub {{ color: #aaa; font-size: 0.7rem; }}
.hbar-track {{ background: #f0f0f0; border-radius: 4px; height: 28px; overflow: visible; position: relative; }}
.hbar-fill {{ height: 100%; border-radius: 4px; min-width: 2px; }}
.hbar-val {{ font-size: 0.78rem; color: #888; }}
.hbar-inline-val {{
  position: absolute; right: -999px; top: 50%; transform: translateY(-50%);
  font-size: 0.75rem; color: #666; white-space: nowrap; padding-left: 8px;
}}
/* Position inline val right of the bar fill */
.hbar-track {{ display: flex; align-items: center; }}
.hbar-inline-val {{ position: static; transform: none; flex-shrink: 0; }}

/* Volume X-axis */
.vol-xaxis {{
  display: flex; justify-content: space-between;
  margin-top: 8px; padding-left: 100px;
  font-size: 0.72rem; color: #aaa;
}}

/* Table */
.table-section {{ margin-top: 28px; }}
.table-title {{ font-size: 0.9rem; font-weight: 600; color: #444; margin-bottom: 10px; }}
.detail-table {{
  width: 100%; border-collapse: collapse; font-size: 0.82rem;
  background: #fff; border: 1px solid #eee; border-radius: 8px; overflow: hidden;
}}
.detail-table th {{
  background: #fafafa; border-bottom: 2px solid #eee;
  padding: 10px 12px; text-align: left;
  color: #666; font-weight: 600; font-size: 0.78rem;
  white-space: nowrap;
}}
.detail-table td {{
  border-bottom: 1px solid #f5f5f5; padding: 9px 12px; vertical-align: middle;
}}
.detail-table tbody tr:hover {{ background: #f8fbff; }}

/* Sort/filter icons in th — NO border, just text icons */
.th-sort, .th-filter {{
  color: #ccc; cursor: pointer; font-size: 0.72rem;
  margin-left: 3px; padding: 0 2px;
  background: none; border: none;
  transition: color 0.15s;
}}
.th-sort:hover, .th-filter:hover {{ color: #1a73e8; }}
.th-sort.active {{ color: #1a73e8; font-weight: bold; }}

.asin-link {{ font-family: 'SF Mono','Consolas',monospace; font-size: 0.78rem; }}
.title-cell {{ color: #666; }}
.price-cell {{ font-weight: 600; }}
.st-ok {{ color: #16a34a; }}
.st-unavailable {{ color: #ea580c; }}
.st-not_found {{ color: #dc2626; }}
.st-error {{ color: #dc2626; }}

/* Filter popup */
.filter-popup {{
  display:none; position:absolute; background:#fff;
  border:1px solid #e0e0e0; border-radius:8px; padding:14px;
  z-index:1000; min-width:200px; max-height:320px; overflow-y:auto;
  box-shadow: 0 4px 16px rgba(0,0,0,0.1);
}}
.filter-popup.show {{ display:block; }}
.filter-popup .fp-hint {{ font-size:0.72rem; color:#aaa; margin-bottom:8px; }}
.filter-popup label {{ display:block; padding:3px 0; font-size:0.82rem; color:#444; cursor:pointer; }}
.filter-popup input[type="checkbox"] {{ margin-right:6px; accent-color:#1a73e8; }}
.filter-popup input[type="number"] {{ width:80px; border:1px solid #ddd; padding:4px 6px; border-radius:4px; font-size:0.8rem; }}
.filter-popup .fp-actions {{ margin-top:10px; display:flex; gap:8px; }}
.filter-popup .fp-btn {{ padding:5px 14px; border-radius:6px; border:none; cursor:pointer; font-size:0.8rem; font-weight:500; }}
.filter-popup .fp-apply {{ background:#1a73e8; color:#fff; }}
.filter-popup .fp-apply:hover {{ background:#1557b0; }}
.filter-popup .fp-clear {{ background:#f0f0f0; color:#555; }}
.filter-popup .fp-clear:hover {{ background:#e0e0e0; }}

.header .sub {{ color: #999; font-size: 0.82rem; margin-top: 4px; }}
canvas {{ width:100%; }}
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
document.querySelectorAll('.tab-btn').forEach(btn => {{
  btn.addEventListener('click', () => {{
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.market-panel').forEach(p => p.style.display='none');
    btn.classList.add('active');
    document.querySelector(`.market-panel[data-market="${{btn.dataset.market}}"]`).style.display='block';
  }});
}});

// Sort
document.querySelectorAll('.th-sort').forEach(el => {{
  el.addEventListener('click', e => {{
    e.stopPropagation();
    const th = el.closest('th');
    const table = th.closest('table');
    const tbody = table.querySelector('tbody');
    const col = parseInt(el.dataset.col);
    const rows = Array.from(tbody.querySelectorAll('tr'));
    const wasAsc = el.classList.contains('asc');
    table.querySelectorAll('.th-sort').forEach(s => {{ s.classList.remove('asc','desc','active'); s.innerHTML='&#8597;'; }});
    const asc = !wasAsc;
    el.classList.add(asc?'asc':'desc','active');
    el.innerHTML = asc?'&#9650;':'&#9660;';
    rows.sort((a,b) => {{
      let va=a.cells[col]?.textContent.trim()||'', vb=b.cells[col]?.textContent.trim()||'';
      const na=parseFloat(va.replace(/[^\\d.\\-]/g,'')), nb=parseFloat(vb.replace(/[^\\d.\\-]/g,''));
      if(!isNaN(na)&&!isNaN(nb)) return asc?na-nb:nb-na;
      return asc?va.localeCompare(vb):vb.localeCompare(va);
    }});
    rows.forEach(r=>tbody.appendChild(r));
  }});
}});

// Filter
const popup = document.getElementById('filterPopup');
let fCol=null, fTable=null;
document.querySelectorAll('.th-filter').forEach(el => {{
  el.addEventListener('click', e => {{
    e.stopPropagation();
    const th=el.closest('th'), table=th.closest('table'), col=parseInt(el.dataset.col);
    fCol=col; fTable=table;
    const rows=Array.from(table.querySelector('tbody').querySelectorAll('tr'));
    const vals=new Set(); let isNum=true;
    rows.forEach(r=>{{
      const v=r.cells[col]?.textContent.trim()||'';
      vals.add(v);
      if(v&&v!=='-'&&isNaN(parseFloat(v.replace(/[^\\d.\\-]/g,'')))) isNum=false;
    }});
    let h='';
    if(isNum&&vals.size>5){{
      h=`<div class="fp-hint">Numeric range</div>
        <label>Min: <input type="number" id="fMin" step="any"></label>
        <label style="margin-top:4px">Max: <input type="number" id="fMax" step="any"></label>
        <div class="fp-actions"><button class="fp-btn fp-apply" onclick="applyNum()">Apply</button><button class="fp-btn fp-clear" onclick="clearF()">Clear</button></div>`;
    }}else{{
      const sorted=Array.from(vals).sort();
      h=`<div class="fp-hint">Select values</div>`;
      sorted.forEach(v=>{{h+=`<label><input type="checkbox" value="${{v.replace(/"/g,'&quot;')}}" checked> ${{v||'(empty)'}}</label>`;}});
      h+=`<div class="fp-actions"><button class="fp-btn fp-apply" onclick="applyTxt()">Apply</button><button class="fp-btn fp-clear" onclick="clearF()">Clear</button></div>`;
    }}
    popup.innerHTML=h;
    const rect=el.getBoundingClientRect();
    popup.style.top=(rect.bottom+window.scrollY+4)+'px';
    popup.style.left=Math.min(rect.left+window.scrollX,window.innerWidth-230)+'px';
    popup.classList.add('show');
  }});
}});
document.addEventListener('click',e=>{{
  if(!popup.contains(e.target)&&!e.target.classList.contains('th-filter')) popup.classList.remove('show');
}});
function applyNum(){{
  const mn=parseFloat(document.getElementById('fMin').value),mx=parseFloat(document.getElementById('fMax').value);
  Array.from(fTable.querySelector('tbody').rows).forEach(r=>{{
    const v=parseFloat((r.cells[fCol]?.textContent||'').replace(/[^\\d.\\-]/g,''));
    let ok=true;
    if(!isNaN(mn)&&(isNaN(v)||v<mn))ok=false;
    if(!isNaN(mx)&&(isNaN(v)||v>mx))ok=false;
    r.style.display=ok?'':'none';
  }});
  popup.classList.remove('show');
}}
function applyTxt(){{
  const ck=new Set(); popup.querySelectorAll('input[type=checkbox]:checked').forEach(c=>ck.add(c.value));
  Array.from(fTable.querySelector('tbody').rows).forEach(r=>{{
    r.style.display=ck.has(r.cells[fCol]?.textContent.trim()||'')?'':'none';
  }});
  popup.classList.remove('show');
}}
function clearF(){{
  Array.from(fTable.querySelector('tbody').rows).forEach(r=>r.style.display='');
  popup.classList.remove('show');
}}

// Volume trend
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
    ctx.strokeStyle='#eee';ctx.lineWidth=0.5;
    for(let i=0;i<=4;i++){{
      const y=pad+(H-2*pad)*(1-i/4);
      ctx.beginPath();ctx.moveTo(pad,y);ctx.lineTo(W-10,y);ctx.stroke();
      ctx.fillStyle='#aaa';ctx.font='10px sans-serif';
      ctx.fillText(Math.round(maxV*i/4).toLocaleString(),2,y+3);
    }}
    ctx.strokeStyle='#1a73e8';ctx.lineWidth=2;ctx.beginPath();
    dates.forEach((d,i)=>{{
      const x=pad+(W-pad-10)*i/(dates.length-1),y=pad+(H-2*pad)*(1-vals[i]/maxV);
      i===0?ctx.moveTo(x,y):ctx.lineTo(x,y);
    }});
    ctx.stroke();
    ctx.fillStyle='#999';ctx.font='9px sans-serif';
    const step=Math.max(1,Math.floor(dates.length/6));
    dates.forEach((d,i)=>{{if(i%step===0||i===dates.length-1){{const x=pad+(W-pad-10)*i/(dates.length-1);ctx.fillText(d,x-15,H-4);}}}});
  }});
}}
</script>
</body>
</html>'''
