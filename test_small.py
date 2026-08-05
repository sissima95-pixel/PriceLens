# -*- coding: utf-8 -*-
"""Small end-to-end test: 5 ASINs from AU file → single market → HTML."""
import sys, time
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')

from pricelens.cli import _read_input
from pricelens.fetcher import fetch_batch
from pricelens.reporter import write_csv, write_html

items = _read_input(r"C:\Users\mqia\Downloads\20260804_074854.xlsx")[:5]
print(f"Testing {len(items)} items on AU")
for it in items:
    print(f"  {it}")

t0 = time.time()
results = fetch_batch(items, ["AU"], max_workers=3, delay_between=0.5)
print(f"Fetched in {time.time()-t0:.1f}s")

out = Path(r"C:\Users\mqia\Documents\asin-pricelens\test_output_au")
out.mkdir(parents=True, exist_ok=True)
ts = time.strftime("%Y%m%d_%H%M%S")
csv_p = write_csv(results, out / f"small_{ts}.csv")
html_p = write_html(results, out / f"small_{ts}.html", title="AU Security Camera · Small Sample")
print(f"CSV: {csv_p}")
print(f"HTML: {html_p}")

for r in results:
    print(f"  {r.asin} @ {r.market}: status={r.status} price={r.price} disp='{r.display_price}' "
          f"brand='{r.brand}' search={r.search_rank} purchase={r.purchase_rank}")
