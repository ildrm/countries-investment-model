#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Iran Investment Macro Model - single-file implementation
=========================================================

Purpose
-------
1) Try to read selected public data from the Central Bank of Iran (CBI).
2) Preserve raw/official observations and their provenance.
3) Fall back to a clearly-labeled seed snapshot when live extraction fails.
4) Allow explicit manual overrides from JSON.
5) Detect a simple Iranian macro regime.
6) Produce MACRO attractiveness scores for:
   - Gold
   - Foreign currency
   - Real estate
   - Equities
   - Fixed income
   - Rial cash
7) Optionally apply a small valuation adjustment when market data is supplied.

IMPORTANT
---------
This is a research/decision-support model, not personalized financial advice.
Without market valuation data, outputs are MACRO_SIGNAL only, not BUY/SELL calls.

Python
------
Python 3.10+

Required packages
-----------------
    pip install requests beautifulsoup4

Optional packages
-----------------
For browser fallback on CBI pages:
    pip install playwright
    playwright install chromium

For XLSX links discovered on CBI:
    pip install openpyxl

Examples
--------
Run with live CBI attempt + seed fallback:
    py iran.py

Run offline using only the built-in seed snapshot:
    py iran.py --no-web

Save JSON report:
    py iran.py --output report.json

Provide manual macro overrides:
    python iran.py --input-json macro.json

Provide optional market valuation inputs:
    python iran.py --market-json market.json

Example macro.json:
{
  "inflation_12m": {
    "value": 61.4,
    "period": "1405-04",
    "release_date": "2026-07-28",
    "source": "manual"
  },
  "inflation_yoy": 83.9,
  "inflation_mom": 3.6,
  "liquidity_growth": 53.3,
  "monetary_base_growth": 61.5,
  "gdp_growth": -0.7,
  "interbank_rate": 23.94
}

Example market.json:
{
  "gold_coin_bubble_pct": 12.0,
  "equity_pe": 7.2,
  "housing_price_to_annual_rent": 22.0,
  "fixed_income_yield": 34.0,
  "deposit_rate": 30.0
}
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import io
import json
import math
import re
import sys

# Force UTF-8 for Python stdout/stderr on Windows and other platforms.
# The human-readable CLI intentionally stays English-only because legacy CMD
# has poor RTL/Persian rendering even when UTF-8 is enabled. JSON output stays
# UTF-8 and may safely contain Persian text.
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional
from urllib.parse import urljoin, urlparse

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError as exc:
    raise SystemExit(
        "Missing dependencies. Install with:\n"
        "  pip install requests beautifulsoup4"
    ) from exc


# =============================================================================
# Configuration
# =============================================================================

CBI_HOME = "https://www.cbi.ir/"
CBI_POLICY_RATES = "https://www.cbi.ir/PolicyRates/policyrates_fa.aspx"
CBI_LATEST_ECONOMIC_DATA = "https://cbi.ir/simplelist/LatestEconomicData_fa.aspx"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/139.0 Safari/537.36"
)

HTTP_TIMEOUT_SECONDS = 25
MAX_DISCOVERED_LINKS = 12

# Built-in snapshot: used ONLY as a fallback if live extraction / manual overrides
# do not provide a metric. These values are deliberately marked as "seed".
# Update/remove them whenever you have newer verified data.
SEED_SNAPSHOT: dict[str, dict[str, Any]] = {
    "inflation_12m": {
        "value": 61.4,
        "unit": "percent",
        "period": "1405-04",
        "release_date": "2026-07-28",
        "frequency": "monthly",
        "source": "CBI-reported seed snapshot",
        "source_url": CBI_LATEST_ECONOMIC_DATA,
        "base_confidence": 0.55,
    },
    "inflation_yoy": {
        "value": 83.9,
        "unit": "percent",
        "period": "1405-04",
        "release_date": "2026-07-28",
        "frequency": "monthly",
        "source": "CBI-reported seed snapshot",
        "source_url": CBI_LATEST_ECONOMIC_DATA,
        "base_confidence": 0.55,
    },
    "inflation_mom": {
        "value": 3.6,
        "unit": "percent",
        "period": "1405-04",
        "release_date": "2026-07-28",
        "frequency": "monthly",
        "source": "CBI-reported seed snapshot",
        "source_url": CBI_LATEST_ECONOMIC_DATA,
        "base_confidence": 0.55,
    },
    "liquidity_growth": {
        "value": 53.3,
        "unit": "percent_yoy",
        "period": "1404-end",
        "release_date": "2026-06-22",
        "frequency": "annual",
        "source": "CBI-reported seed snapshot",
        "source_url": CBI_LATEST_ECONOMIC_DATA,
        "base_confidence": 0.50,
    },
    "monetary_base_growth": {
        "value": 61.5,
        "unit": "percent_yoy",
        "period": "1404-end",
        "release_date": "2026-06-22",
        "frequency": "annual",
        "source": "CBI-reported seed snapshot",
        "source_url": CBI_LATEST_ECONOMIC_DATA,
        "base_confidence": 0.50,
    },
    "gdp_growth": {
        "value": -0.7,
        "unit": "percent_real",
        "period": "1404",
        "release_date": "2026-06-23",
        "frequency": "annual",
        "source": "CBI-reported seed snapshot",
        "source_url": CBI_LATEST_ECONOMIC_DATA,
        "base_confidence": 0.50,
    },
    "interbank_rate": {
        "value": 23.94,
        "unit": "percent",
        "period": "1405-05-14",
        "release_date": "2026-08-05",
        "frequency": "weekly",
        "source": "CBI-reported seed snapshot",
        "source_url": CBI_POLICY_RATES,
        "base_confidence": 0.55,
    },
}

# Candidate Persian labels. The scraper intentionally uses multiple variants
# because CBI wording/layout may change over time.
METRIC_LABELS: dict[str, list[str]] = {
    "interbank_rate": [
        "نرخ سود بازار بین بانکی",
        "نرخ بازار بین بانکی",
        "بازار بین بانکی",
    ],
    "repo_rate": [
        "نرخ توافق بازخرید",
        "توافق بازخرید",
        "ریپو",
    ],
    "corridor_floor": [
        "حداقل نرخ سود",
        "کف دالان",
        "کف کریدور",
    ],
    "corridor_ceiling": [
        "حداکثر نرخ سود",
        "سقف دالان",
        "سقف کریدور",
    ],
    "inflation_12m": [
        "تورم دوازده ماهه",
        "تورم 12 ماهه",
        "نرخ تورم سالانه",
    ],
    "inflation_yoy": [
        "تورم نقطه به نقطه",
        "تورم نقطه‌به‌نقطه",
        "نقطه به نقطه",
    ],
    "inflation_mom": [
        "تورم ماهانه",
    ],
    "liquidity_growth": [
        "رشد نقدینگی",
        "نرخ رشد نقدینگی",
    ],
    "monetary_base_growth": [
        "رشد پایه پولی",
        "نرخ رشد پایه پولی",
    ],
    "gdp_growth": [
        "رشد تولید ناخالص داخلی",
        "رشد اقتصادی",
        "نرخ رشد تولید ناخالص داخلی",
    ],
}

PERSIAN_DIGITS = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789",
)

ARABIC_CHAR_NORMALIZATION = str.maketrans({
    "ي": "ی",
    "ك": "ک",
    "\u200c": " ",  # ZWNJ
    "\u200f": " ",
    "\u200e": " ",
})


# =============================================================================
# Data structures
# =============================================================================

@dataclass
class Observation:
    metric: str
    value: float
    unit: str = "percent"
    period: Optional[str] = None
    release_date: Optional[str] = None  # ISO Gregorian if known
    frequency: str = "unknown"
    source: str = "unknown"
    source_url: Optional[str] = None
    source_kind: str = "unknown"  # live_cbi | manual | seed
    base_confidence: float = 0.5
    extraction_note: Optional[str] = None

    @property
    def age_days(self) -> Optional[int]:
        if not self.release_date:
            return None
        try:
            d = dt.date.fromisoformat(self.release_date)
        except ValueError:
            return None
        return max(0, (dt.date.today() - d).days)

    @property
    def staleness_factor(self) -> float:
        """
        1.0 = fresh. Approaches 0 as observation becomes stale.
        Half-life depends on frequency.
        """
        age = self.age_days
        if age is None:
            return 0.75

        half_life = {
            "daily": 10,
            "weekly": 28,
            "monthly": 75,
            "quarterly": 180,
            "annual": 365,
            "unknown": 120,
        }.get(self.frequency, 120)

        return math.exp(-math.log(2) * age / half_life)

    @property
    def effective_confidence(self) -> float:
        return clamp(self.base_confidence * self.staleness_factor, 0.0, 1.0)

    def as_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        d["age_days"] = self.age_days
        d["staleness_factor"] = round(self.staleness_factor, 4)
        d["effective_confidence"] = round(self.effective_confidence, 4)
        return d


@dataclass
class FetchResult:
    url: str
    ok: bool
    text: str = ""
    content: bytes = b""
    content_type: str = ""
    status_code: Optional[int] = None
    method: str = "requests"
    error: Optional[str] = None


@dataclass
class AssetResult:
    asset: str
    macro_score: float
    valuation_adjustment: float
    final_score: float
    signal: str
    scope: str
    confidence: float
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "asset": self.asset,
            "macro_score": round(self.macro_score, 2),
            "valuation_adjustment": round(self.valuation_adjustment, 2),
            "final_score": round(self.final_score, 2),
            "signal": self.signal,
            "scope": self.scope,
            "confidence": round(self.confidence, 4),
            "reasons": self.reasons,
        }


# =============================================================================
# Utilities
# =============================================================================

def clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    s = str(value)
    s = s.translate(PERSIAN_DIGITS)
    s = s.translate(ARABIC_CHAR_NORMALIZATION)
    s = s.replace("٪", "%")
    s = s.replace("٫", ".")
    s = s.replace("٬", ",")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def parse_number(value: Any) -> Optional[float]:
    """
    Parses Persian/Arabic/Latin numeric strings.
    Supports commas and percent signs. Returns the first plausible number.
    """
    s = normalize_text(value)
    if not s:
        return None

    # Negative numbers may be written as (12.3)
    paren_negative = bool(re.search(r"\(\s*[\d.,]+\s*\)", s))

    matches = re.findall(r"[-+]?\d[\d,]*(?:\.\d+)?", s)
    if not matches:
        return None

    for token in matches:
        token = token.replace(",", "")
        try:
            num = float(token)
            if paren_negative and num > 0:
                num = -num
            return num
        except ValueError:
            continue
    return None


def extract_numbers(value: Any) -> list[float]:
    s = normalize_text(value)
    tokens = re.findall(r"[-+]?\d[\d,]*(?:\.\d+)?", s)
    out: list[float] = []
    for token in tokens:
        try:
            out.append(float(token.replace(",", "")))
        except ValueError:
            pass
    return out


def metric_unit(metric: str) -> str:
    if metric in {"liquidity_growth", "monetary_base_growth"}:
        return "percent_yoy"
    if metric == "gdp_growth":
        return "percent_real"
    return "percent"


def metric_frequency(metric: str) -> str:
    return {
        "interbank_rate": "weekly",
        "repo_rate": "weekly",
        "corridor_floor": "weekly",
        "corridor_ceiling": "weekly",
        "inflation_12m": "monthly",
        "inflation_yoy": "monthly",
        "inflation_mom": "monthly",
        "liquidity_growth": "monthly",
        "monetary_base_growth": "monthly",
        "gdp_growth": "quarterly",
    }.get(metric, "unknown")


def signal_label(score: float) -> str:
    if score >= 75:
        return "STRONG_POSITIVE"
    if score >= 60:
        return "POSITIVE"
    if score >= 45:
        return "NEUTRAL"
    if score >= 30:
        return "WEAK"
    return "VERY_WEAK"


def score01(raw_minus1_to_plus1: float) -> float:
    return clamp(50.0 + 50.0 * clamp(raw_minus1_to_plus1), 0.0, 100.0)


def weighted_mean(values: Iterable[tuple[float, float]]) -> float:
    pairs = [(v, w) for v, w in values if w > 0]
    total_w = sum(w for _, w in pairs)
    if total_w == 0:
        return 0.0
    return sum(v * w for v, w in pairs) / total_w


# =============================================================================
# HTTP / Browser client
# =============================================================================

class CBIClient:
    def __init__(self, debug: bool = False) -> None:
        self.debug = debug
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Connection": "keep-alive",
        })

        try:
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry

            retries = Retry(
                total=2,
                connect=2,
                read=2,
                backoff_factor=0.7,
                status_forcelist=(429, 500, 502, 503, 504),
                allowed_methods=frozenset(["GET"]),
            )
            self.session.mount("https://", HTTPAdapter(max_retries=retries))
            self.session.mount("http://", HTTPAdapter(max_retries=retries))
        except Exception:
            pass

    def _log(self, msg: str) -> None:
        if self.debug:
            print(f"[debug] {msg}", file=sys.stderr)

    def fetch_requests(self, url: str) -> FetchResult:
        try:
            self._log(f"GET {url}")
            r = self.session.get(url, timeout=HTTP_TIMEOUT_SECONDS, allow_redirects=True)
            content_type = r.headers.get("content-type", "").lower()

            # CBI may use legacy encodings; requests' guess often works better
            # than blindly trusting a bad header.
            if "text" in content_type or "html" in content_type:
                if not r.encoding or r.encoding.lower() in {"iso-8859-1", "ascii"}:
                    r.encoding = r.apparent_encoding or "utf-8"
                text = r.text
            else:
                text = ""

            return FetchResult(
                url=url,
                ok=r.ok,
                text=text,
                content=r.content,
                content_type=content_type,
                status_code=r.status_code,
                method="requests",
                error=None if r.ok else f"HTTP {r.status_code}",
            )
        except Exception as exc:
            return FetchResult(
                url=url,
                ok=False,
                method="requests",
                error=f"{type(exc).__name__}: {exc}",
            )

    def fetch_playwright(self, url: str) -> FetchResult:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return FetchResult(
                url=url,
                ok=False,
                method="playwright",
                error="Playwright is not installed",
            )

        try:
            self._log(f"Playwright GET {url}")
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(
                    user_agent=USER_AGENT,
                    locale="fa-IR",
                )
                response = page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=HTTP_TIMEOUT_SECONDS * 1000,
                )
                page.wait_for_timeout(1200)
                text = page.content()
                status = response.status if response else None
                browser.close()

            return FetchResult(
                url=url,
                ok=(status is None or 200 <= status < 400),
                text=text,
                content=text.encode("utf-8", errors="ignore"),
                content_type="text/html",
                status_code=status,
                method="playwright",
            )
        except Exception as exc:
            return FetchResult(
                url=url,
                ok=False,
                method="playwright",
                error=f"{type(exc).__name__}: {exc}",
            )

    def fetch(self, url: str, browser_fallback: bool = True) -> FetchResult:
        result = self.fetch_requests(url)
        if result.ok and result.text:
            return result

        if browser_fallback:
            browser = self.fetch_playwright(url)
            if browser.ok and browser.text:
                return browser
            if not result.error:
                result.error = browser.error
            else:
                result.error += f"; fallback: {browser.error}"

        return result


# =============================================================================
# CBI extraction
# =============================================================================

def html_rows(html: str) -> list[list[str]]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[list[str]] = []

    for tr in soup.select("tr"):
        cells = [
            normalize_text(cell.get_text(" ", strip=True))
            for cell in tr.select("th,td")
        ]
        cells = [c for c in cells if c]
        if cells:
            rows.append(cells)

    # Also include list items / blocks as fallback context.
    for selector in ("li", "p", "div"):
        for node in soup.select(selector):
            txt = normalize_text(node.get_text(" ", strip=True))
            if 3 <= len(txt) <= 500:
                rows.append([txt])

    return rows


def choose_plausible_metric_value(metric: str, numbers: list[float]) -> Optional[float]:
    """
    Heuristic only. It intentionally rejects values that are likely years/dates.
    """
    if not numbers:
        return None

    ranges = {
        "inflation_12m": (-10, 300),
        "inflation_yoy": (-20, 500),
        "inflation_mom": (-30, 100),
        "liquidity_growth": (-50, 300),
        "monetary_base_growth": (-100, 500),
        "gdp_growth": (-50, 50),
        "interbank_rate": (0, 100),
        "repo_rate": (0, 100),
        "corridor_floor": (0, 100),
        "corridor_ceiling": (0, 100),
    }
    lo, hi = ranges.get(metric, (-1000, 1000))

    candidates = [
        n for n in numbers
        if lo <= n <= hi
        and not (1300 <= abs(n) <= 1500)
        and not (1900 <= abs(n) <= 2200)
    ]

    if not candidates:
        return None

    # In many RTL tables, the newest value is not guaranteed to be the visual
    # "last" column. Prefer the value nearest the matched label in row-level
    # extraction; when we only have a bag of candidates, the final candidate is
    # a practical fallback and the observation gets reduced confidence.
    return candidates[-1]


def extract_metric_from_rows(
    metric: str,
    rows: list[list[str]],
) -> Optional[tuple[float, str]]:
    labels = [normalize_text(x) for x in METRIC_LABELS.get(metric, [])]

    for row in rows:
        normalized_cells = [normalize_text(c) for c in row]
        row_text = " | ".join(normalized_cells)

        if not any(label in row_text for label in labels):
            continue

        # First try values from individual cells, preferring cells that are not
        # the label cell itself.
        for cell in reversed(normalized_cells):
            if any(label in cell for label in labels):
                continue
            numbers = extract_numbers(cell)
            value = choose_plausible_metric_value(metric, numbers)
            if value is not None:
                return value, f"matched table/block row: {row_text[:300]}"

        # Then try the whole row.
        numbers = extract_numbers(row_text)
        value = choose_plausible_metric_value(metric, numbers)
        if value is not None:
            return value, f"matched row context: {row_text[:300]}"

    return None


def extract_metrics_from_html(
    html: str,
    source_url: str,
    source_method: str,
    metrics: Iterable[str],
) -> dict[str, Observation]:
    rows = html_rows(html)
    found: dict[str, Observation] = {}

    for metric in metrics:
        result = extract_metric_from_rows(metric, rows)
        if result is None:
            continue

        value, note = result
        found[metric] = Observation(
            metric=metric,
            value=value,
            unit=metric_unit(metric),
            frequency=metric_frequency(metric),
            source=f"Central Bank of Iran ({source_method})",
            source_url=source_url,
            source_kind="live_cbi",
            base_confidence=0.82,
            extraction_note=note,
        )

    return found


def same_cbi_domain(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == "cbi.ir" or host.endswith(".cbi.ir")


def discover_economic_links(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    keywords = [
        "تورم",
        "نقدینگی",
        "پایه پولی",
        "تولید ناخالص",
        "رشد اقتصادی",
        "نماگر",
        "آمار اقتصادی",
        "گزیده آمار",
        "economic",
        "xlsx",
        "xls",
    ]

    scored: list[tuple[int, str]] = []
    seen: set[str] = set()

    for a in soup.select("a[href]"):
        href = urljoin(base_url, a.get("href", ""))
        if not same_cbi_domain(href) or href in seen:
            continue
        seen.add(href)

        text = normalize_text(a.get_text(" ", strip=True) + " " + href)
        score = sum(1 for kw in keywords if normalize_text(kw).lower() in text.lower())
        if score > 0:
            scored.append((score, href))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [url for _, url in scored[:MAX_DISCOVERED_LINKS]]


def extract_metrics_from_xlsx(
    content: bytes,
    source_url: str,
    metrics: Iterable[str],
) -> dict[str, Observation]:
    try:
        import openpyxl
    except ImportError:
        return {}

    found: dict[str, Observation] = {}

    try:
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception:
        return {}

    for ws in wb.worksheets:
        rows: list[list[str]] = []
        try:
            for row in ws.iter_rows(values_only=True):
                cells = [normalize_text(v) for v in row if v is not None]
                if cells:
                    rows.append(cells)
        except Exception:
            continue

        for metric in metrics:
            if metric in found:
                continue
            result = extract_metric_from_rows(metric, rows)
            if result:
                value, note = result
                found[metric] = Observation(
                    metric=metric,
                    value=value,
                    unit=metric_unit(metric),
                    frequency=metric_frequency(metric),
                    source=f"Central Bank of Iran XLSX ({ws.title})",
                    source_url=source_url,
                    source_kind="live_cbi",
                    base_confidence=0.78,
                    extraction_note=note,
                )

    return found


def scrape_cbi(debug: bool = False) -> tuple[dict[str, Observation], list[str]]:
    client = CBIClient(debug=debug)
    observations: dict[str, Observation] = {}
    warnings: list[str] = []

    # 1) Policy-rate page
    policy = client.fetch(CBI_POLICY_RATES, browser_fallback=True)
    if policy.ok and policy.text:
        observations.update(
            extract_metrics_from_html(
                policy.text,
                CBI_POLICY_RATES,
                policy.method,
                ["interbank_rate", "repo_rate", "corridor_floor", "corridor_ceiling"],
            )
        )
    else:
        warnings.append(
            f"Could not fetch CBI policy-rate page: {policy.error or 'unknown error'}"
        )

    # Be polite to the public site.
    time.sleep(0.25)

    # 2) Latest economic data index
    latest = client.fetch(CBI_LATEST_ECONOMIC_DATA, browser_fallback=True)
    if latest.ok and latest.text:
        observations.update(
            extract_metrics_from_html(
                latest.text,
                CBI_LATEST_ECONOMIC_DATA,
                latest.method,
                [
                    "inflation_12m",
                    "inflation_yoy",
                    "inflation_mom",
                    "liquidity_growth",
                    "monetary_base_growth",
                    "gdp_growth",
                ],
            )
        )

        # The index may only link to data files/pages. Discover a small,
        # bounded number of relevant links.
        missing = [
            m for m in (
                "inflation_12m",
                "inflation_yoy",
                "inflation_mom",
                "liquidity_growth",
                "monetary_base_growth",
                "gdp_growth",
            )
            if m not in observations
        ]

        if missing:
            links = discover_economic_links(latest.text, CBI_LATEST_ECONOMIC_DATA)
            for link in links:
                if not missing:
                    break
                time.sleep(0.20)
                fetched = client.fetch(link, browser_fallback=False)
                if not fetched.ok:
                    continue

                ctype = fetched.content_type
                lower_url = link.lower()

                if "spreadsheet" in ctype or lower_url.endswith((".xlsx", ".xls")):
                    newly = extract_metrics_from_xlsx(fetched.content, link, missing)
                elif fetched.text:
                    newly = extract_metrics_from_html(
                        fetched.text, link, fetched.method, missing
                    )
                else:
                    newly = {}

                observations.update(newly)
                missing = [m for m in missing if m not in observations]
    else:
        warnings.append(
            f"Could not fetch CBI latest-economic-data page: {latest.error or 'unknown error'}"
        )

    return observations, warnings


# =============================================================================
# Manual/seed observation merge
# =============================================================================

def observation_from_mapping(
    metric: str,
    raw: Any,
    source_kind: str,
) -> Observation:
    if isinstance(raw, (int, float)):
        return Observation(
            metric=metric,
            value=float(raw),
            unit=metric_unit(metric),
            frequency=metric_frequency(metric),
            source=source_kind,
            source_kind=source_kind,
            base_confidence=0.95 if source_kind == "manual" else 0.55,
        )

    if not isinstance(raw, dict):
        raise ValueError(f"Invalid override for {metric}: expected number or object")

    if "value" not in raw:
        raise ValueError(f"Invalid override for {metric}: missing 'value'")

    return Observation(
        metric=metric,
        value=float(raw["value"]),
        unit=str(raw.get("unit", metric_unit(metric))),
        period=raw.get("period"),
        release_date=raw.get("release_date"),
        frequency=str(raw.get("frequency", metric_frequency(metric))),
        source=str(raw.get("source", source_kind)),
        source_url=raw.get("source_url"),
        source_kind=source_kind,
        base_confidence=float(
            raw.get(
                "base_confidence",
                0.95 if source_kind == "manual" else 0.55,
            )
        ),
        extraction_note=raw.get("extraction_note"),
    )


def load_json(path: Optional[str]) -> dict[str, Any]:
    if not path:
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def merge_observations(
    live: dict[str, Observation],
    manual_data: dict[str, Any],
    use_seed: bool,
) -> tuple[dict[str, Observation], list[str]]:
    """
    Precedence: manual > live CBI > built-in seed.
    """
    out = dict(live)
    warnings: list[str] = []

    if use_seed:
        for metric, raw in SEED_SNAPSHOT.items():
            if metric not in out:
                obs = observation_from_mapping(metric, raw, "seed")
                out[metric] = obs
                warnings.append(
                    f"{metric}: live value unavailable; using built-in seed "
                    f"({obs.period or 'unknown period'})."
                )

    for metric, raw in manual_data.items():
        out[metric] = observation_from_mapping(metric, raw, "manual")

    return out, warnings


# =============================================================================
# Macro model
# =============================================================================

def get_value(obs: dict[str, Observation], metric: str) -> Optional[float]:
    item = obs.get(metric)
    return None if item is None else item.value


def feature_or_zero(value: Optional[float]) -> float:
    return 0.0 if value is None else value


def macro_features(obs: dict[str, Observation]) -> dict[str, Any]:
    inflation = get_value(obs, "inflation_12m")
    inflation_yoy = get_value(obs, "inflation_yoy")
    liquidity = get_value(obs, "liquidity_growth")
    monetary_base = get_value(obs, "monetary_base_growth")
    growth = get_value(obs, "gdp_growth")
    interbank = get_value(obs, "interbank_rate")

    inflation_level = feature_or_zero(inflation)
    growth_level = feature_or_zero(growth)

    # Use the more aggressive monetary expansion signal when both are known.
    money_candidates = [x for x in (liquidity, monetary_base) if x is not None]
    money_growth = max(money_candidates) if money_candidates else 0.0

    real_rate_proxy = None
    if interbank is not None and inflation is not None:
        # This is a rough "ex-post style" proxy, not a theoretically pure
        # expected real policy rate.
        real_rate_proxy = interbank - inflation

    # All normalized features are in [-1, +1].
    # Positive means "more of the named pressure/strength".
    inflation_pressure = clamp((inflation_level - 15.0) / 45.0)
    inflation_acceleration = 0.0
    if inflation_yoy is not None and inflation is not None:
        inflation_acceleration = clamp((inflation_yoy - inflation) / 40.0)

    money_pressure = clamp((money_growth - 20.0) / 40.0)
    growth_strength = clamp(growth_level / 5.0)

    negative_real_rate_pressure = 0.0
    if real_rate_proxy is not None:
        negative_real_rate_pressure = clamp((-real_rate_proxy) / 40.0)

    currency_debasement_pressure = clamp(
        0.45 * inflation_pressure
        + 0.35 * money_pressure
        + 0.20 * negative_real_rate_pressure
    )

    return {
        "inflation_12m": inflation,
        "inflation_yoy": inflation_yoy,
        "liquidity_growth": liquidity,
        "monetary_base_growth": monetary_base,
        "gdp_growth": growth,
        "interbank_rate": interbank,
        "real_rate_proxy": real_rate_proxy,
        "normalized": {
            "inflation_pressure": inflation_pressure,
            "inflation_acceleration": inflation_acceleration,
            "money_pressure": money_pressure,
            "growth_strength": growth_strength,
            "negative_real_rate_pressure": negative_real_rate_pressure,
            "currency_debasement_pressure": currency_debasement_pressure,
        },
    }


def detect_regime(features: dict[str, Any]) -> dict[str, Any]:
    inflation = features["inflation_12m"]
    growth = features["gdp_growth"]
    real_rate = features["real_rate_proxy"]
    liquidity = features["liquidity_growth"]
    base = features["monetary_base_growth"]

    # Missing-data-safe regime rules.
    if inflation is None or growth is None:
        return {
            "name": "INSUFFICIENT_DATA",
            "confidence": 0.20,
            "explanation": "Inflation and GDP growth are required for regime detection.",
        }

    money_growth = max(x for x in [liquidity, base, 0.0] if x is not None)

    if (
        inflation >= 40
        and growth <= 0
        and money_growth >= 30
        and real_rate is not None
        and real_rate <= -10
    ):
        return {
            "name": "STAGFLATION_DEBASEMENT",
            "confidence": 0.92,
            "explanation": (
                "Very high inflation + non-positive real growth + rapid monetary "
                "expansion + deeply negative real-rate proxy."
            ),
        }

    if inflation >= 25 and growth <= 0:
        return {
            "name": "STAGFLATION",
            "confidence": 0.85,
            "explanation": "High inflation combined with weak/non-positive real growth.",
        }

    if inflation >= 20 and growth > 0:
        return {
            "name": "INFLATIONARY_GROWTH",
            "confidence": 0.80,
            "explanation": "Positive real growth with elevated inflation.",
        }

    if inflation < 15 and growth < 0:
        return {
            "name": "DEFLATIONARY_RECESSION",
            "confidence": 0.75,
            "explanation": "Weak/negative growth with comparatively low inflation.",
        }

    return {
        "name": "NORMAL_GROWTH",
        "confidence": 0.65,
        "explanation": "No extreme stagflation/debasement rule was triggered.",
    }


def overall_data_confidence(obs: dict[str, Observation]) -> float:
    core_weights = {
        "inflation_12m": 0.22,
        "inflation_yoy": 0.08,
        "liquidity_growth": 0.16,
        "monetary_base_growth": 0.16,
        "gdp_growth": 0.20,
        "interbank_rate": 0.18,
    }
    values: list[tuple[float, float]] = []
    for metric, weight in core_weights.items():
        if metric in obs:
            values.append((obs[metric].effective_confidence, weight))
    return clamp(weighted_mean(values), 0.0, 1.0)


def macro_asset_scores(
    features: dict[str, Any],
    confidence: float,
) -> dict[str, AssetResult]:
    n = features["normalized"]

    inf = n["inflation_pressure"]
    inf_acc = n["inflation_acceleration"]
    money = n["money_pressure"]
    growth = n["growth_strength"]
    neg_real = n["negative_real_rate_pressure"]
    debase = n["currency_debasement_pressure"]

    # Raw scores: approximately [-1, +1].
    raw: dict[str, float] = {
        # Monetary/inflation hedge, with extra benefit from negative real rates.
        "gold": (
            0.28 * inf
            + 0.13 * inf_acc
            + 0.22 * money
            + 0.22 * neg_real
            + 0.15 * debase
        ),

        # Currency hedge. Valuation cannot be inferred from CBI macro data alone.
        "foreign_currency": (
            0.34 * inf
            + 0.26 * money
            + 0.20 * neg_real
            + 0.20 * debase
        ),

        # Real asset but recession/financing conditions can hurt.
        "real_estate": (
            0.30 * inf
            + 0.27 * money
            + 0.20 * neg_real
            + 0.13 * debase
            + 0.10 * growth
        ),

        # Inflation/liquidity can support nominal earnings, while weak real
        # growth hurts. This is intentionally less extreme and should later be
        # replaced by sector/company-level scoring.
        "equities": (
            0.20 * inf
            + 0.20 * money
            + 0.18 * neg_real
            + 0.12 * debase
            + 0.30 * growth
        ),

        # Nominal fixed income is penalized by high inflation and negative
        # real-rate conditions.
        "fixed_income": (
            -0.42 * inf
            -0.18 * money
            -0.30 * neg_real
            + 0.10 * growth
        ),

        # Rial cash is primarily a purchasing-power preservation score here.
        "rial_cash": (
            -0.48 * inf
            -0.22 * money
            -0.22 * neg_real
            -0.08 * debase
        ),
    }

    reasons: dict[str, list[str]] = {
        "gold": [
            "High inflation increases demand for purchasing-power hedges.",
            "Rapid monetary expansion supports debasement risk.",
            "Negative real-rate conditions reduce the relative appeal of nominal rial assets.",
        ],
        "foreign_currency": [
            "High domestic inflation raises long-run pressure on the rial's purchasing power.",
            "Rapid monetary expansion increases currency-debasement pressure.",
            "CBI macro data alone cannot determine whether the current free-market FX price is cheap or expensive.",
        ],
        "real_estate": [
            "Real assets can hedge inflation over long horizons.",
            "Monetary expansion supports nominal asset prices.",
            "Weak real growth can reduce affordability, transactions and rental strength.",
        ],
        "equities": [
            "Inflation/liquidity can support nominal corporate revenues and replacement values.",
            "Negative real growth is a headwind.",
            "Iran equities should be analyzed by sector/company; exporters and regulated domestic firms can behave very differently.",
        ],
        "fixed_income": [
            "High inflation reduces the purchasing power of nominal fixed coupons.",
            "Deeply negative real-rate conditions are unfavorable for purchasing-power preservation.",
        ],
        "rial_cash": [
            "This score measures purchasing-power preservation, not liquidity convenience.",
            "High inflation and monetary expansion are major headwinds for uninvested rial cash.",
        ],
    }

    return {
        asset: AssetResult(
            asset=asset,
            macro_score=score01(clamp(raw_score)),
            valuation_adjustment=0.0,
            final_score=score01(clamp(raw_score)),
            signal=signal_label(score01(clamp(raw_score))),
            scope="MACRO_ONLY",
            confidence=confidence,
            reasons=reasons[asset],
        )
        for asset, raw_score in raw.items()
    }


# =============================================================================
# Optional valuation layer
# =============================================================================

def apply_market_valuation(
    assets: dict[str, AssetResult],
    market: dict[str, Any],
    inflation_12m: Optional[float],
) -> None:
    """
    Applies modest adjustments only. Macro and valuation remain separately
    visible so the user can audit the decision.

    Supported market keys:
      gold_coin_bubble_pct
      equity_pe
      housing_price_to_annual_rent
      fixed_income_yield
      deposit_rate

    These are heuristics for version 1, not immutable economic laws.
    """

    def add(asset: str, adj: float, reason: str) -> None:
        item = assets[asset]
        item.valuation_adjustment += adj
        item.final_score = clamp(item.macro_score + item.valuation_adjustment, 0, 100)
        item.signal = signal_label(item.final_score)
        item.scope = "MACRO_PLUS_VALUATION"
        item.reasons.append(reason)

    if "gold_coin_bubble_pct" in market:
        bubble = float(market["gold_coin_bubble_pct"])
        # Negative/low bubble is supportive; very large bubble is a penalty.
        adj = clamp((5.0 - bubble) / 25.0) * 20.0
        add(
            "gold",
            adj,
            f"Gold/coin domestic premium input={bubble:.2f}% -> valuation adjustment {adj:+.1f}.",
        )

    if "equity_pe" in market:
        pe = float(market["equity_pe"])
        # A coarse Iran-market heuristic. Sector composition matters.
        adj = clamp((8.0 - pe) / 6.0) * 15.0
        add(
            "equities",
            adj,
            f"Equity P/E input={pe:.2f} -> coarse valuation adjustment {adj:+.1f}.",
        )

    if "housing_price_to_annual_rent" in market:
        ratio = float(market["housing_price_to_annual_rent"])
        adj = clamp((18.0 - ratio) / 12.0) * 15.0
        add(
            "real_estate",
            adj,
            f"Housing price/annual-rent ratio={ratio:.2f} -> valuation adjustment {adj:+.1f}.",
        )

    if "fixed_income_yield" in market and inflation_12m is not None:
        ytm = float(market["fixed_income_yield"])
        real_yield_proxy = ytm - inflation_12m
        adj = clamp(real_yield_proxy / 25.0) * 20.0
        add(
            "fixed_income",
            adj,
            f"Fixed-income yield={ytm:.2f}%, inflation={inflation_12m:.2f}% "
            f"-> real-yield proxy={real_yield_proxy:.2f}% and adjustment {adj:+.1f}.",
        )

    if "deposit_rate" in market and inflation_12m is not None:
        rate = float(market["deposit_rate"])
        real_rate_proxy = rate - inflation_12m
        adj = clamp(real_rate_proxy / 25.0) * 20.0
        add(
            "rial_cash",
            adj,
            f"Deposit/cash-like rate={rate:.2f}%, inflation={inflation_12m:.2f}% "
            f"-> real-rate proxy={real_rate_proxy:.2f}% and adjustment {adj:+.1f}.",
        )


# =============================================================================
# Reporting
# =============================================================================

ASSET_LABELS = {
    "gold": "Gold",
    "foreign_currency": "Foreign Currency",
    "real_estate": "Real Estate",
    "equities": "Equities",
    "fixed_income": "Fixed Income",
    "rial_cash": "Rial Cash",
}

SIGNAL_LABELS = {
    "STRONG_POSITIVE": "Strong Positive",
    "POSITIVE": "Positive",
    "NEUTRAL": "Neutral",
    "WEAK": "Weak",
    "VERY_WEAK": "Very Weak",
}


def build_report(
    observations: dict[str, Observation],
    fetch_warnings: list[str],
    merge_warnings: list[str],
    market_data: dict[str, Any],
) -> dict[str, Any]:
    features = macro_features(observations)
    regime = detect_regime(features)
    data_conf = overall_data_confidence(observations)

    # Combine data confidence and rule-regime confidence.
    analysis_conf = clamp(
        0.75 * data_conf + 0.25 * float(regime["confidence"]),
        0.0,
        1.0,
    )

    assets = macro_asset_scores(features, analysis_conf)
    apply_market_valuation(
        assets,
        market_data,
        inflation_12m=features["inflation_12m"],
    )

    ranked = sorted(
        (item.as_dict() for item in assets.values()),
        key=lambda x: x["final_score"],
        reverse=True,
    )

    warnings = list(fetch_warnings) + list(merge_warnings)

    if not market_data:
        warnings.append(
            "No market valuation inputs supplied. Asset outputs are MACRO_ONLY, "
            "not entry-price BUY/SELL recommendations."
        )

    if any(o.source_kind == "seed" for o in observations.values()):
        warnings.append(
            "At least one built-in seed value was used. Refresh/override seed "
            "data before production or capital-allocation use."
        )

    return {
        "model": {
            "name": "Iran Investment Macro Model",
            "version": "1.0.0",
            "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "scope": "macro regime + optional lightweight valuation heuristics",
            "disclaimer": (
                "Research/decision-support only; not personalized financial advice."
            ),
        },
        "regime": regime,
        "data_confidence": round(data_conf, 4),
        "analysis_confidence": round(analysis_conf, 4),
        "features": features,
        "observations": {
            metric: obs.as_dict()
            for metric, obs in sorted(observations.items())
        },
        "market_inputs": market_data,
        "assets_ranked": ranked,
        "warnings": warnings,
    }


def print_human_report(report: dict[str, Any]) -> None:
    """
    Windows-friendly terminal report.

    The CLI intentionally uses English labels only because legacy CMD has poor
    RTL/Persian rendering even when UTF-8 is enabled. The JSON report is still
    written as proper UTF-8 with ensure_ascii=False.
    """
    regime = report["regime"]
    features = report["features"]

    print("=" * 78)
    print("Iran Investment Macro Model")
    print("=" * 78)
    print(f"Regime             : {regime['name']}")
    print(f"Regime confidence  : {regime['confidence']:.0%}")
    print(f"Data confidence    : {report['data_confidence']:.0%}")
    print(f"Analysis confidence: {report['analysis_confidence']:.0%}")
    print(f"Reason             : {regime['explanation']}")
    print()

    print("Core macro snapshot")
    print("-" * 78)
    core = [
        ("12m inflation", features.get("inflation_12m")),
        ("YoY inflation", features.get("inflation_yoy")),
        ("Liquidity growth", features.get("liquidity_growth")),
        ("Monetary-base growth", features.get("monetary_base_growth")),
        ("Real GDP growth", features.get("gdp_growth")),
        ("Interbank rate", features.get("interbank_rate")),
        ("Real-rate proxy", features.get("real_rate_proxy")),
    ]
    for name, value in core:
        formatted = "N/A" if value is None else f"{value:.2f}%"
        print(f"{name:<26}: {formatted}")

    print()
    print("Asset ranking")
    print("-" * 78)
    print(f"{'Asset':<22} {'Macro':>8} {'ValAdj':>8} {'Final':>8} {'Signal':>20}")
    for item in report["assets_ranked"]:
        label = ASSET_LABELS.get(item["asset"], item["asset"])
        sig = SIGNAL_LABELS.get(item["signal"], item["signal"])
        print(
            f"{label:<22} "
            f"{item['macro_score']:>8.1f} "
            f"{item['valuation_adjustment']:>+8.1f} "
            f"{item['final_score']:>8.1f} "
            f"{sig:>20}"
        )

    print()
    print("Warnings")
    print("-" * 78)
    if report["warnings"]:
        for warning in report["warnings"]:
            print(f"- {warning}")
    else:
        print("- None")

    print()
    print(
        "Note: MACRO_ONLY means the model has not determined whether the "
        "current market entry price is cheap or expensive."
    )


# =============================================================================
# CLI
# =============================================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Single-file macro investment regime model for Iran."
    )
    parser.add_argument(
        "--no-web",
        action="store_true",
        help="Do not access CBI; use manual/seed data only.",
    )
    parser.add_argument(
        "--no-seed",
        action="store_true",
        help="Do not use the built-in fallback seed snapshot.",
    )
    parser.add_argument(
        "--input-json",
        help="JSON file with manual macro overrides.",
    )
    parser.add_argument(
        "--market-json",
        help="JSON file with optional market valuation inputs.",
    )
    parser.add_argument(
        "--output",
        help="Write the complete JSON report to this file.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON report instead of the human-readable report.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print fetch/debug details to stderr.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        manual_data = load_json(args.input_json)
        market_data = load_json(args.market_json)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2

    live: dict[str, Observation] = {}
    fetch_warnings: list[str] = []

    if not args.no_web:
        live, fetch_warnings = scrape_cbi(debug=args.debug)

    try:
        observations, merge_warnings = merge_observations(
            live=live,
            manual_data=manual_data,
            use_seed=not args.no_seed,
        )
    except (TypeError, ValueError) as exc:
        print(f"Override error: {exc}", file=sys.stderr)
        return 2

    required = {
        "inflation_12m",
        "liquidity_growth",
        "monetary_base_growth",
        "gdp_growth",
        "interbank_rate",
    }
    missing_required = sorted(required - set(observations))
    if missing_required:
        fetch_warnings.append(
            "Missing core metrics: " + ", ".join(missing_required)
        )

    report = build_report(
        observations=observations,
        fetch_warnings=fetch_warnings,
        merge_warnings=merge_warnings,
        market_data=market_data,
    )

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_human_report(report)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
