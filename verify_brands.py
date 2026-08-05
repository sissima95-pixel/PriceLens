# -*- coding: utf-8 -*-
"""Verify brand extraction for known cases."""
import sys
sys.stdout.reconfigure(encoding='utf-8')

from pricelens.fetcher import MarketSession

TESTS = [
    ("B09JZ5BG26", "AU", "Ring"),       # Ring cam — old /X/b/ URL
    ("B0CCYP6KFM", "AU", "eufy"),       # eufy — /stores/eufy/page/
    ("B07XLML2YS", "AU", "Tapo"),       # Tapo — /stores/
    ("B0CLRNPYD4", "AU", "COCOCAM"),    # COCOCAM
    ("B0CDSLBHQX", "AU", "Blurams"),    # blurams
    ("B0BQJVKVQR", "AU", "Tapo"),       # Tapo
    ("B07X81M2D2", "AU", "Reolink"),    # Reolink
]

s = MarketSession("AU")
s.prepare()

print(f"{'ASIN':<12} {'Expected':<15} {'Got':<30} {'Title (first 60 chars)'}")
print("-" * 120)
for asin, mk, expected in TESTS:
    r = s.fetch(asin)
    ok = "✅" if expected.lower() in r.brand.lower() else "❌"
    print(f"{ok} {asin:<10} {expected:<15} {r.brand[:29]:<30} {r.title[:60]}")
