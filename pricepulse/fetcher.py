# -*- coding: utf-8 -*-
"""ASIN PricePulse 价格脉搏 — Core price fetcher.

Technique:
  1. Warm-up GET homepage → obtain session cookies
  2. POST /portal-migration/hz/glow/address-change with a local zipcode
     → Amazon associates the session with a local delivery address
  3. Set i18n-prefs cookie to force local currency display
  4. GET /dp/{ASIN} → extract price from HTML

Key insight: Amazon geo-fences product pages by *delivery address*, not by
IP. Once the session has a local delivery zip + currency preference cookie,
the product page returns native local price regardless of egress IP.
"""
from __future__ import annotations

import re
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict, field
from typing import Iterable

import requests

log = logging.getLogger(__name__)

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# ---------------------------------------------------------------------------
# Marketplace configuration
# ---------------------------------------------------------------------------
MARKETS: dict[str, dict] = {
    "US": {"host": "www.amazon.com",    "zip": "10001",    "lang": "en-US,en;q=0.9", "currency": "USD"},
    "UK": {"host": "www.amazon.co.uk",  "zip": "SW1A 1AA", "lang": "en-GB,en;q=0.9", "currency": "GBP"},
    "DE": {"host": "www.amazon.de",     "zip": "10115",    "lang": "de-DE,de;q=0.9", "currency": "EUR"},
    "FR": {"host": "www.amazon.fr",     "zip": "75001",    "lang": "fr-FR,fr;q=0.9", "currency": "EUR"},
    "IT": {"host": "www.amazon.it",     "zip": "00184",    "lang": "it-IT,it;q=0.9", "currency": "EUR"},
    "ES": {"host": "www.amazon.es",     "zip": "28001",    "lang": "es-ES,es;q=0.9", "currency": "EUR"},
    "NL": {"host": "www.amazon.nl",     "zip": "1012 JS",  "lang": "nl-NL,nl;q=0.9", "currency": "EUR"},
    "SE": {"host": "www.amazon.se",     "zip": "111 20",   "lang": "sv-SE,sv;q=0.9", "currency": "SEK"},
    "PL": {"host": "www.amazon.pl",     "zip": "00-001",   "lang": "pl-PL,pl;q=0.9", "currency": "PLN"},
    "JP": {"host": "www.amazon.co.jp",  "zip": "100-0001", "lang": "ja-JP,ja;q=0.9", "currency": "JPY"},
    "CA": {"host": "www.amazon.ca",     "zip": "M5H 2N2",  "lang": "en-CA,en;q=0.9", "currency": "CAD"},
    "AU": {"host": "www.amazon.com.au", "zip": "2000",     "lang": "en-AU,en;q=0.9", "currency": "AUD"},
    "AE": {"host": "www.amazon.ae",     "zip": "00000",    "lang": "en-AE,en;q=0.9", "currency": "AED"},
    "SA": {"host": "www.amazon.sa",     "zip": "11564",    "lang": "en-SA,en;q=0.9", "currency": "SAR"},
    "SG": {"host": "www.amazon.sg",     "zip": "018956",   "lang": "en-SG,en;q=0.9", "currency": "SGD"},
    "IN": {"host": "www.amazon.in",     "zip": "110001",   "lang": "en-IN,en;q=0.9", "currency": "INR"},
    "MX": {"host": "www.amazon.com.mx", "zip": "06600",    "lang": "es-MX,es;q=0.9", "currency": "MXN"},
    "BR": {"host": "www.amazon.com.br", "zip": "01310-100","lang": "pt-BR,pt;q=0.9", "currency": "BRL"},
    "TR": {"host": "www.amazon.com.tr", "zip": "34000",    "lang": "tr-TR,tr;q=0.9", "currency": "TRY"},
}


@dataclass
class PriceResult:
    asin: str
    market: str
    currency: str
    price: float | None = None
    display_price: str = ""
    title: str = ""
    brand: str = ""
    availability: str = ""
    delivery_location: str = ""
    url: str = ""
    error: str = ""
    status: str = "unknown"  # ok | not_found | unavailable | error
    # Optional per-input metadata (carried through from source file if present)
    search_rank: float | None = None
    purchase_rank: float | None = None
    search_volume: float | None = None  # single snapshot number
    volume_series: dict | None = None    # time-series {"2023-01": 500, ...}


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------
class MarketSession:
    """One prepared requests.Session per (marketplace) — cookies preloaded
    with delivery address + currency. Reusable across many ASIN fetches."""

    def __init__(self, market: str):
        if market not in MARKETS:
            raise ValueError(f"Unknown market: {market}. "
                             f"Available: {list(MARKETS.keys())}")
        self.market = market
        self.cfg = MARKETS[market]
        self.host = self.cfg["host"]
        self.base = f"https://{self.host}"
        self.currency = self.cfg["currency"]
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                      "image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": self.cfg["lang"],
            "Accept-Encoding": "gzip, deflate, br",
        })
        self._prepared = False

    def prepare(self) -> bool:
        """Warm up + set delivery address + set currency cookie.
        Returns True if the session is ready for product-page fetching."""
        domain = "." + self.host.replace("www.", "")
        # Pre-set currency cookie
        self.session.cookies.set("i18n-prefs", self.currency, domain=domain)

        # Warmup
        try:
            self.session.get(self.base + "/", timeout=25)
        except Exception as e:
            log.warning("[%s] warmup failed: %s", self.market, e)
            return False

        # POST delivery-address change
        payload = {
            "locationType": "LOCATION_INPUT",
            "zipCode": self.cfg["zip"],
            "storeContext": "generic",
            "deviceType": "web",
            "pageType": "Gateway",
            "actionSource": "glow",
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            "Referer": self.base + "/",
            "Origin": self.base,
            "X-Requested-With": "XMLHttpRequest",
        }
        try:
            r = self.session.post(
                f"{self.base}/portal-migration/hz/glow/address-change?actionSource=glow",
                data=payload, headers=headers, timeout=25,
            )
            j = r.json()
            if j.get("isAddressUpdated") != 1:
                log.warning("[%s] address change rejected: %s",
                            self.market, j)
        except Exception as e:
            log.warning("[%s] address change error: %s", self.market, e)
            # We still try to fetch — some markets may work without explicit
            # address change (e.g., where the default is already local).

        # Re-set currency cookie (address-change response may reset it)
        self.session.cookies.set("i18n-prefs", self.currency, domain=domain)
        self._prepared = True
        return True

    def fetch(self, asin: str) -> PriceResult:
        """Fetch one ASIN's product page and extract price."""
        if not self._prepared:
            self.prepare()

        result = PriceResult(
            asin=asin, market=self.market, currency=self.currency,
            url=f"{self.base}/dp/{asin}",
        )
        try:
            r = self.session.get(
                f"{self.base}/dp/{asin}/?th=1", timeout=25,
            )
        except Exception as e:
            result.error = f"{type(e).__name__}: {e}"
            result.status = "error"
            return result

        if r.status_code == 404:
            result.status = "not_found"
            result.error = "HTTP 404 — ASIN does not exist in this market"
            return result
        if r.status_code != 200:
            result.status = "error"
            result.error = f"HTTP {r.status_code}"
            return result

        html = r.text
        _parse_price(html, result)
        return result


# ---------------------------------------------------------------------------
# HTML parsing
# ---------------------------------------------------------------------------
_PRICE_PATTERNS = [
    # priceAmount is the most reliable JSON-embedded float
    (r'"priceAmount"\s*:\s*([\d.]+)', "priceAmount"),
]
_DISPLAY_PATTERNS = [
    (r'id="corePrice_feature_div"[\s\S]{0,3000}?a-offscreen[^>]*>([^<]+)<',
     "corePrice"),
    (r'id="corePriceDisplay_desktop_feature_div"[\s\S]{0,3000}?a-offscreen[^>]*>([^<]+)<',
     "corePriceDisplay"),
    (r'id="apex_desktop"[\s\S]{0,3000}?a-offscreen[^>]*>([^<]+)<',
     "apex_desktop"),
]
_TITLE_PATTERN = re.compile(r'id="productTitle"[^>]*>\s*([^<]+)', re.S)
# /stores/BRAND/page/ (new-style Amazon brand store URL)
_BRAND_STORE_URL_NEW = re.compile(r'href="[^"]*/stores/([^/"]+)/page/', re.S)
# /BRAND/b/ref=... (old-style Amazon brand store URL, e.g. Ring, Amazon)
_BRAND_STORE_URL_OLD = re.compile(
    r'id="bylineInfo"[^>]*href="/([^/"]+)/b/ref=', re.S)
# Anchor text of the bylineInfo link — matches "Visit the X Store" pattern etc.
_BRAND_ANCHOR = re.compile(
    r'id="bylineInfo"[^>]*>\s*([^<]+?)\s*</a>', re.S)
# JSON payload sometimes contains "brand":"X"
_BRAND_JSON = re.compile(r'"brand"\s*:\s*"([^"]+)"')
# Product-detail table row: "Brand: XXX" or table cell after Brand label
_BRAND_TABLE = re.compile(
    r'>\s*(?:Brand|Marka|Marca|Marque|Marke|Merk|\u30d6\u30e9\u30f3\u30c9|'
    r'\u54c1\u724c|\u30e1\u30fc\u30ab\u30fc)\s*'
    r'(?:</span>\s*<span[^>]*>|:\s*|</td>\s*<td[^>]*>|</th>\s*<td[^>]*>)'
    r'\s*([^<\n]+?)\s*</', re.S)


# Common "brand-line" suffixes that form a 2-word brand identity
# (e.g. "Amazon Basics", "eufy Security", "Google Nest")
_BRAND_LINE_SUFFIXES = {
    "basics", "essentials", "security", "home", "prime", "kids",
    "pro", "nest", "smart", "life", "care", "sport", "sports",
    "audio", "cam", "music",
}
# Words that are NEVER a brand (fallback shouldn't return these)
_BRAND_BLOCKLIST = {
    "the", "new", "genuine", "original", "official", "premium",
    "brand", "no", "one", "1pack", "2pack", "3pack", "twin", "pack",
    "amazon",  # "Amazon" alone is rarely the brand people care about
}


def _title_first_words(title: str) -> str:
    """Extract likely brand from title.

    Amazon convention: brand is the first token in the title. This function
    returns just the first word — unless the second word is a common
    'brand-line' suffix (Basics, Security, Nest, etc.), in which case it
    returns "Word1 Word2".
    """
    if not title:
        return ""
    # Strip HTML entities & split at first strong delimiter
    t = (title
         .replace("&amp;", "&").replace("&#39;", "'")
         .replace("&quot;", '"'))
    t = re.split(r'[|,:\(\[]', t, maxsplit=1)[0].strip()
    words = t.split()
    if not words:
        return ""

    first = words[0].strip(" .,'\"")
    # First word must look like a brand (no digits, not blocklisted)
    if re.search(r'\d', first) or first.lower() in _BRAND_BLOCKLIST:
        return ""
    # Model-code words (all-caps + digits) — skip
    if len(first) <= 2 and first.isupper():
        return ""

    # Check if second word forms a compound brand
    if len(words) >= 2:
        second = words[1].strip(" .,'\"")
        if second.lower() in _BRAND_LINE_SUFFIXES and not re.search(r'\d', second):
            return f"{first} {second}"

    return first
_LOCATION_PATTERN = re.compile(
    r'glow-ingress-line2[^>]*>\s*([^<]+)', re.S)

_UNAVAILABLE_PHRASES = [
    "Currently unavailable",
    "Zurzeit nicht verf",
    "cannot be dispatched",
    "This item cannot be shipped",
    "Actuellement indisponible",
    "Attualmente non disponibile",
    "Actualmente no disponible",
    "\u5546\u54c1\u306e\u53d6\u308a\u6271\u3044",  # JP: 商品の取り扱い
]


def _clean(s: str) -> str:
    return (s or "").replace("\u200c", "").replace("&zwnj;", "").strip()


def _parse_price(html: str, result: PriceResult) -> None:
    # Title
    m = _TITLE_PATTERN.search(html)
    if m:
        result.title = _clean(m.group(1))[:200]
    # Brand extraction — strategy (revised 2026-08-11):
    #   Primary: byline / storefront (authoritative brand attribution from Amazon)
    #   Fallback: title first words (only when byline is unavailable)
    #
    # Previous title-first approach failed for categories where listings
    # start with descriptive words (e.g. "Portable Fan", "Wireless Camera").
    # Byline-first is more reliable across all categories.
    brand = ""

    # 1. Byline anchor text ("Visit the X Store")
    m = _BRAND_ANCHOR.search(html)
    if m:
        b = _clean(m.group(1))
        b = re.sub(
            r'^(Visit the|Besuche den|Visita la|Visitez la|Visitez le|'
            r'Bezoek de|Visita la Store di|Ir a la tienda de|'
            r'\u30d6\u30e9\u30f3\u30c9\u30b9\u30c8\u30a2|'
            r'Marca:|Marque:|Brand:|Marka:)\s*',
            '', b, flags=re.I)
        b = re.sub(
            r'\s*(Store|-Store|-Shop|\u306e\u30b9\u30c8\u30a2|Storefront)\s*$',
            '', b, flags=re.I)
        if b and len(b) < 60:
            brand = b.strip()

    # 2. Store URL (new style: /stores/BRAND/page/)
    if not brand:
        m = _BRAND_STORE_URL_NEW.search(html)
        if m:
            brand = _clean(m.group(1)).replace("-", " ")

    # 3. Store URL (old style: /BRAND/b/ref=)
    if not brand:
        m = _BRAND_STORE_URL_OLD.search(html)
        if m:
            slug = _clean(m.group(1))
            if slug and len(slug) > 1 and slug.lower() not in ("sp", "s", "gp", "b"):
                brand = slug.replace("-", " ")

    # 4. Product detail table ("Brand: X")
    if not brand:
        m = _BRAND_TABLE.search(html)
        if m:
            b = _clean(m.group(1))
            if b and len(b) < 60 and not any(x in b.lower() for x in
                ("category", "amazon", "this item")):
                brand = b

    # 5. JSON payload ("brand":"X")
    if not brand:
        m = _BRAND_JSON.search(html)
        if m:
            brand = _clean(m.group(1))

    # 6. Last resort: title first words
    if not brand and result.title:
        brand = _title_first_words(result.title)

    result.brand = brand[:80]
    # Delivery location (for verification)
    m = _LOCATION_PATTERN.search(html)
    if m:
        result.delivery_location = _clean(m.group(1))[:80]

    # Availability
    lower = html.lower()[:200000]
    for phrase in _UNAVAILABLE_PHRASES:
        if phrase.lower() in lower:
            result.availability = "unavailable"
            result.status = "unavailable"
            return
    result.availability = "in_stock"

    # Price (numeric)
    for pat, _name in _PRICE_PATTERNS:
        m = re.search(pat, html)
        if m:
            try:
                result.price = float(m.group(1))
                break
            except ValueError:
                pass

    # Display string
    for pat, _name in _DISPLAY_PATTERNS:
        m = re.search(pat, html)
        if m and m.group(1).strip():
            result.display_price = _clean(m.group(1))[:40]
            break

    if result.price is not None or result.display_price:
        result.status = "ok"
    else:
        result.status = "unavailable"
        if not result.availability:
            result.availability = "no_price_found"


# ---------------------------------------------------------------------------
# Batch orchestration
# ---------------------------------------------------------------------------
def fetch_batch(
    asins: Iterable,
    markets: Iterable[str],
    max_workers: int = 8,
    delay_between: float = 0.3,
    progress_callback=None,
) -> list[PriceResult]:
    """Fetch a list of ASINs across a list of markets.

    Args:
        asins: iterable — either strings (ASINs), or dicts with keys
            {"asin": ..., "search_rank": ..., "purchase_rank": ...}
        markets: iterable of market codes (US, DE, UK, ...)
        max_workers: parallel threads per market
        delay_between: seconds between requests within one market session
        progress_callback: optional fn(done, total, market, asin) for CLI progress

    Returns list of PriceResult, one per (asin, market) combination.
    Any metadata in dict inputs (search_rank, purchase_rank) is carried through.
    """
    # Normalize input to list of dicts
    normalized: list[dict] = []
    seen = set()
    for item in asins:
        if isinstance(item, str):
            a = item.strip().upper()
            if not a or a in seen:
                continue
            seen.add(a)
            normalized.append({"asin": a})
        elif isinstance(item, dict):
            a = str(item.get("asin", "")).strip().upper()
            if not a or a in seen:
                continue
            seen.add(a)
            normalized.append({
                "asin": a,
                "search_rank": item.get("search_rank"),
                "purchase_rank": item.get("purchase_rank"),
                "search_volume": item.get("search_volume"),
                "volume_series": item.get("volume_series"),
            })

    markets = [m.strip().upper() for m in markets if m and m.strip()]
    for m in markets:
        if m not in MARKETS:
            raise ValueError(
                f"Unknown market '{m}'. Available: {sorted(MARKETS.keys())}"
            )

    total = len(normalized) * len(markets)
    done = [0]
    all_results: list[PriceResult] = []

    for market in markets:
        session = MarketSession(market)
        session.prepare()
        log.info("[%s] session prepared", market)

        def _one(item):
            time.sleep(delay_between)
            r = session.fetch(item["asin"])
            # Attach optional metadata
            r.search_rank = item.get("search_rank")
            r.purchase_rank = item.get("purchase_rank")
            r.search_volume = item.get("search_volume")
            r.volume_series = item.get("volume_series")
            return r

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {ex.submit(_one, it): it["asin"] for it in normalized}
            for fut in as_completed(futures):
                r = fut.result()
                all_results.append(r)
                done[0] += 1
                if progress_callback:
                    progress_callback(done[0], total, market, r.asin)

    return all_results


def results_to_dicts(results: list[PriceResult]) -> list[dict]:
    return [asdict(r) for r in results]
