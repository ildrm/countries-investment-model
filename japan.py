#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Japan Investment Macro Model
==================================

Single-file country model.

Pipeline
--------
Official central-bank / central-bank-hosted data
    -> raw observations
    -> confidence + staleness
    -> macro features
    -> economic regime
    -> asset macro scores
    -> optional valuation adjustments
    -> console / JSON report

The terminal output is English-only for reliable Windows CMD rendering.

Required
--------
    py -m pip install requests beautifulsoup4

Recommended for BOJ PDF releases:
    py -m pip install pypdf

Examples
--------
    py japan.py
    py japan.py --no-web
    py japan.py --output report.json
    py japan.py --input-json macro.json
    py japan.py --market-json market.json
    py japan.py --json

Manual macro override example
-----------------------------
{
  "inflation_yoy": 2.5,
  "gdp_growth": 1.2,
  "policy_rate": 3.0,
  "money_growth": 5.0
}

Optional market valuation example
---------------------------------
{
  "gold_premium_pct": 2.0,
  "equity_forward_pe": 17.0,
  "housing_price_to_annual_rent": 22.0,
  "government_bond_yield": 4.0,
  "cash_rate": 3.5,
  "local_currency_reer_overvaluation_pct": 5.0
}

Notes
-----
- Manual values override live values.
- Live values override built-in seed values.
- Seed values are fallbacks only and are explicitly labelled.
- A macro score is NOT a price-entry BUY/SELL recommendation.
- Central banks often reference statistics produced by national statistical
  agencies. Where a central-bank site does not originate a macro series, the
  model may use a clearly-labelled official auxiliary observation as fallback.
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import datetime as dt
import io
import json
import math
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional
from urllib.parse import urljoin

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError as exc:
    raise SystemExit(
        "Missing dependencies. Install with:\n"
        "  py -m pip install requests beautifulsoup4"
    ) from exc

# Reliable UTF-8 writes; human CLI stays ASCII/English-only.
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


COUNTRY = "Japan"
COUNTRY_CODE = "JP"
CURRENCY = "JPY"
CENTRAL_BANK = "Bank of Japan (BOJ)"

# This is the normalization reference used by the regime engine.
# For China it is explicitly a model reference rather than a formal target.
INFLATION_REFERENCE = 2.0
INFLATION_REFERENCE_NOTE = "2% is the Bank of Japan price-stability target."
GROWTH_SCALE = 2.0
MONEY_NEUTRAL_GROWTH = 3.0
MONEY_GROWTH_SCALE = 6.0

HTTP_TIMEOUT = 25
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0 Safari/537.36"
)

ASSET_LABELS = {
    "gold": "Gold",
    "foreign_currency": "Foreign Currency",
    "real_estate": "Real Estate",
    "equities": "Equities",
    "government_bonds": "Government Bonds",
    "local_cash": "JPY Cash",
}

SIGNAL_LABELS = {
    "STRONG_POSITIVE": "Strong Positive",
    "POSITIVE": "Positive",
    "NEUTRAL": "Neutral",
    "WEAK": "Weak",
    "VERY_WEAK": "Very Weak",
}

SEED_SNAPSHOT = {'inflation_yoy': {'value': 2.5, 'unit': 'percent_forecast_ex_fresh_food', 'period': 'FY2026', 'release_date': '2026-07-31', 'frequency': 'quarterly', 'source': 'Bank of Japan - July 2026 Outlook median forecast', 'source_url': 'https://www.boj.or.jp/en/mopo/outlook/', 'base_confidence': 0.91}, 'gdp_growth': {'value': 0.6, 'unit': 'percent_fy_forecast', 'period': 'FY2026', 'release_date': '2026-07-31', 'frequency': 'quarterly', 'source': 'Bank of Japan - July 2026 Outlook median forecast', 'source_url': 'https://www.boj.or.jp/en/mopo/outlook/', 'base_confidence': 0.91}, 'policy_rate': {'value': 1.0, 'unit': 'percent', 'period': '2026-07-31', 'release_date': '2026-07-31', 'frequency': 'event', 'source': 'Bank of Japan - Statement on Monetary Policy', 'source_url': 'https://www.boj.or.jp/en/mopo/mpmdeci/state_2026/index.htm', 'base_confidence': 0.98}, 'money_growth': {'value': 2.2, 'unit': 'percent_yoy', 'period': '2026-07', 'release_date': '2026-08-11', 'frequency': 'monthly', 'source': 'Bank of Japan - Money Stock', 'source_url': 'https://www.boj.or.jp/en/statistics/money/ms/index.htm', 'base_confidence': 0.9}}


@dataclass
class Observation:
    metric: str
    value: float
    unit: str = "percent"
    period: Optional[str] = None
    release_date: Optional[str] = None
    frequency: str = "unknown"
    source: str = "unknown"
    source_url: Optional[str] = None
    source_kind: str = "unknown"  # live_central_bank | official_auxiliary | manual | seed
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
        age = self.age_days
        if age is None:
            return 0.78
        half_life = {
            "daily": 12,
            "weekly": 35,
            "monthly": 95,
            "quarterly": 200,
            "annual": 420,
            "unknown": 150,
        }.get(self.frequency, 150)
        return math.exp(-math.log(2) * age / half_life)

    @property
    def effective_confidence(self) -> float:
        return clamp01(self.base_confidence * self.staleness_factor)

    def as_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        d["age_days"] = self.age_days
        d["staleness_factor"] = round(self.staleness_factor, 4)
        d["effective_confidence"] = round(self.effective_confidence, 4)
        return d


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


def clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    s = str(value).replace("\u00a0", " ").replace("\u202f", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def parse_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    s = normalize_text(value).replace(",", "")
    m = re.search(r"[-+]?\d+(?:\.\d+)?", s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def today_iso() -> str:
    return dt.date.today().isoformat()


def score100(raw: float) -> float:
    return max(0.0, min(100.0, 50.0 + 50.0 * clamp(raw)))


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


class HttpClient:
    def __init__(self, debug: bool = False) -> None:
        self.debug = debug
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml,text/csv,*/*;q=0.8",
        })
        try:
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry
            retries = Retry(
                total=2,
                connect=2,
                read=2,
                backoff_factor=0.6,
                status_forcelist=(429, 500, 502, 503, 504),
                allowed_methods=frozenset(["GET"]),
            )
            adapter = HTTPAdapter(max_retries=retries)
            self.session.mount("https://", adapter)
            self.session.mount("http://", adapter)
        except Exception:
            pass

    def get(self, url: str, params: Optional[dict[str, Any]] = None) -> requests.Response:
        if self.debug:
            print(f"[debug] GET {url} params={params or {}}", file=sys.stderr)
        r = self.session.get(
            url,
            params=params,
            timeout=HTTP_TIMEOUT,
            allow_redirects=True,
        )
        r.raise_for_status()
        if not r.encoding or r.encoding.lower() in {"iso-8859-1", "ascii"}:
            r.encoding = r.apparent_encoding or "utf-8"
        return r


def obs(
    metric: str,
    value: float,
    *,
    period: Optional[str],
    frequency: str,
    source: str,
    source_url: str,
    source_kind: str = "live_central_bank",
    base_confidence: float = 0.90,
    unit: str = "percent",
    note: Optional[str] = None,
) -> Observation:
    return Observation(
        metric=metric,
        value=float(value),
        unit=unit,
        period=period,
        release_date=today_iso() if source_kind.startswith("live") else None,
        frequency=frequency,
        source=source,
        source_url=source_url,
        source_kind=source_kind,
        base_confidence=base_confidence,
        extraction_note=note,
    )


def optional_pdf_text(content: bytes) -> Optional[str]:
    """Return PDF text when pypdf is installed; otherwise return None."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    try:
        reader = PdfReader(io.BytesIO(content))
        chunks = []
        for page in reader.pages:
            chunks.append(page.extract_text() or "")
        return "\n".join(chunks)
    except Exception:
        return None



BOJ_POLICY_INDEX = "https://www.boj.or.jp/en/mopo/mpmdeci/state_2026/index.htm"
BOJ_OUTLOOK_INDEX = "https://www.boj.or.jp/en/mopo/outlook/index.htm"
BOJ_MONEY_STOCK = "https://www.boj.or.jp/en/statistics/money/ms/index.htm"

def _first_pdf_link(client: HttpClient, index_url: str, text_needles: list[str]) -> Optional[str]:
    r = client.get(index_url)
    soup = BeautifulSoup(r.text, "html.parser")
    for a in soup.select("a[href]"):
        text = normalize_text(a.get_text(" ", strip=True)).lower()
        href = urljoin(r.url, a.get("href", ""))
        if href.lower().endswith(".pdf") and all(x.lower() in text for x in text_needles):
            return href
    return None

def fetch_live(client: HttpClient) -> tuple[dict[str, Observation], list[str]]:
    out: dict[str, Observation] = {}
    warnings: list[str] = []

    # Latest BOJ policy statement. PDF extraction is optional; seeds remain
    # available when pypdf is not installed.
    try:
        pdf_url = _first_pdf_link(client, BOJ_POLICY_INDEX, ["statement", "monetary policy"])
        if pdf_url:
            rr = client.get(pdf_url)
            text = optional_pdf_text(rr.content)
            if text:
                clean = normalize_text(text)
                patterns = [
                    r"uncollateralized overnight call rate.*?around\s*([0-9]+(?:\.[0-9]+)?)\s*percent",
                    r"short-term interest rate.*?([0-9]+(?:\.[0-9]+)?)\s*percent",
                ]
                rate = None
                for p in patterns:
                    m = re.search(p, clean, flags=re.I | re.S)
                    if m:
                        rate = float(m.group(1))
                        break
                if rate is not None:
                    out["policy_rate"] = obs(
                        "policy_rate", rate, period="latest MPM", frequency="event",
                        source="Bank of Japan - latest Statement on Monetary Policy",
                        source_url=pdf_url, base_confidence=0.98,
                    )
            else:
                warnings.append(
                    "BOJ latest policy PDF found but pypdf is not installed; seed policy value retained."
                )
    except Exception as exc:
        warnings.append(f"BOJ policy retrieval failed: {exc}")

    # Latest Outlook PDF: attempt to extract FY2026 median GDP/CPI forecasts.
    try:
        pdf_url = _first_pdf_link(client, BOJ_OUTLOOK_INDEX, ["full text"])
        if pdf_url:
            rr = client.get(pdf_url)
            text = optional_pdf_text(rr.content)
            if text:
                clean = normalize_text(text)
                # Forecast tables are layout-sensitive; only accept conservative
                # patterns and otherwise retain the seed.
                gdp_match = re.search(
                    r"Fiscal 2026.{0,900}?Real GDP.{0,180}?\[?\+?([0-9]+\.[0-9]+)\]?",
                    clean, flags=re.I | re.S
                )
                cpi_match = re.search(
                    r"Fiscal 2026.{0,1200}?CPI \(all items less fresh food\).{0,260}?\[?\+?([0-9]+\.[0-9]+)\]?",
                    clean, flags=re.I | re.S
                )
                if gdp_match:
                    out["gdp_growth"] = obs(
                        "gdp_growth", float(gdp_match.group(1)), period="FY2026",
                        frequency="quarterly",
                        source="Bank of Japan - latest Outlook Report",
                        source_url=pdf_url, base_confidence=0.78,
                        unit="percent_fy_forecast",
                        note="Automatically parsed forecast table; inspect provenance before production use.",
                    )
                if cpi_match:
                    out["inflation_yoy"] = obs(
                        "inflation_yoy", float(cpi_match.group(1)), period="FY2026",
                        frequency="quarterly",
                        source="Bank of Japan - latest Outlook Report",
                        source_url=pdf_url, base_confidence=0.78,
                        unit="percent_forecast_ex_fresh_food",
                        note="Automatically parsed forecast table; inspect provenance before production use.",
                    )
    except Exception as exc:
        warnings.append(f"BOJ Outlook retrieval failed: {exc}")

    # Money-stock page: locate the newest PDF and parse M2 y/y when possible.
    try:
        r = client.get(BOJ_MONEY_STOCK)
        soup = BeautifulSoup(r.text, "html.parser")
        pdfs = []
        for a in soup.select("a[href]"):
            text = normalize_text(a.get_text(" ", strip=True)).lower()
            href = urljoin(r.url, a.get("href", ""))
            if href.lower().endswith(".pdf") and ("money stock" in text or "preliminary" in text):
                pdfs.append(href)
        if pdfs:
            rr = client.get(pdfs[0])
            text = optional_pdf_text(rr.content)
            if text:
                clean = normalize_text(text)
                m = re.search(
                    r"M2.{0,500}?(?:year-on-year|y/y|YoY).{0,120}?([0-9]+(?:\.[0-9]+)?)",
                    clean, flags=re.I | re.S
                )
                if m:
                    out["money_growth"] = obs(
                        "money_growth", float(m.group(1)), period="latest",
                        frequency="monthly", source="Bank of Japan - Money Stock",
                        source_url=pdfs[0], base_confidence=0.72,
                        note="PDF table auto-parse; seed is preferred if this value looks implausible.",
                    )
    except Exception as exc:
        warnings.append(f"BOJ money-stock retrieval failed: {exc}")

    return out, warnings



def observation_from_mapping(metric: str, raw: Any, source_kind: str) -> Observation:
    if isinstance(raw, (int, float)):
        return Observation(
            metric=metric,
            value=float(raw),
            source=source_kind,
            source_kind=source_kind,
            base_confidence=0.96 if source_kind == "manual" else 0.65,
        )

    if not isinstance(raw, dict) or "value" not in raw:
        raise ValueError(f"Invalid observation for {metric}")

    return Observation(
        metric=metric,
        value=float(raw["value"]),
        unit=str(raw.get("unit", "percent")),
        period=raw.get("period"),
        release_date=raw.get("release_date"),
        frequency=str(raw.get("frequency", "unknown")),
        source=str(raw.get("source", source_kind)),
        source_url=raw.get("source_url"),
        source_kind=source_kind,
        base_confidence=float(
            raw.get("base_confidence", 0.96 if source_kind == "manual" else 0.65)
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
    manual: dict[str, Any],
    use_seed: bool,
) -> tuple[dict[str, Observation], list[str]]:
    # Precedence: manual > live > seed.
    merged: dict[str, Observation] = {}
    warnings: list[str] = []

    if use_seed:
        for metric, raw in SEED_SNAPSHOT.items():
            merged[metric] = observation_from_mapping(metric, raw, "seed")

    for metric, item in live.items():
        merged[metric] = item

    for metric, raw in manual.items():
        merged[metric] = observation_from_mapping(metric, raw, "manual")

    if use_seed:
        for metric, item in merged.items():
            if item.source_kind == "seed":
                warnings.append(
                    f"{metric}: using seed fallback ({item.period or 'period unknown'})."
                )
    return merged, warnings


def getv(data: dict[str, Observation], key: str) -> Optional[float]:
    item = data.get(key)
    return item.value if item else None


def macro_features(data: dict[str, Observation]) -> dict[str, Any]:
    inflation = getv(data, "inflation_yoy")
    core_inflation = getv(data, "core_inflation")
    growth = getv(data, "gdp_growth")
    policy = getv(data, "policy_rate")
    money = getv(data, "money_growth")

    inflation_gap = None if inflation is None else inflation - INFLATION_REFERENCE
    real_rate_proxy = None if policy is None or inflation is None else policy - inflation

    inflation_pressure = 0.0 if inflation_gap is None else clamp(inflation_gap / 4.0)
    disinflation_pressure = 0.0 if inflation_gap is None else clamp(-inflation_gap / 3.0)
    growth_strength = 0.0 if growth is None else clamp(growth / GROWTH_SCALE)

    money_impulse = 0.0
    if money is not None:
        money_impulse = clamp(
            (money - MONEY_NEUTRAL_GROWTH) / MONEY_GROWTH_SCALE
        )

    real_rate_strength = 0.0
    if real_rate_proxy is not None:
        real_rate_strength = clamp(real_rate_proxy / 4.0)

    easing_pressure = clamp(-real_rate_strength)
    restrictive_pressure = clamp(real_rate_strength)

    return {
        "inflation_yoy": inflation,
        "core_inflation": core_inflation,
        "gdp_growth": growth,
        "policy_rate": policy,
        "money_growth": money,
        "inflation_reference": INFLATION_REFERENCE,
        "inflation_gap": inflation_gap,
        "real_rate_proxy": real_rate_proxy,
        "normalized": {
            "inflation_pressure": inflation_pressure,
            "disinflation_pressure": disinflation_pressure,
            "growth_strength": growth_strength,
            "money_impulse": money_impulse,
            "real_rate_strength": real_rate_strength,
            "easing_pressure": easing_pressure,
            "restrictive_pressure": restrictive_pressure,
        },
    }


def detect_regime(features: dict[str, Any]) -> dict[str, Any]:
    inf = features["inflation_yoy"]
    growth = features["gdp_growth"]

    if inf is None or growth is None:
        return {
            "name": "INSUFFICIENT_DATA",
            "confidence": 0.25,
            "explanation": "Inflation and real-growth observations are required.",
        }

    gap = inf - INFLATION_REFERENCE

    if growth < 0 and gap >= 1.0:
        return {
            "name": "STAGFLATION",
            "confidence": 0.88,
            "explanation": "Real activity is contracting while inflation is materially above reference.",
        }

    if growth <= 0.75 and gap >= 0.75:
        return {
            "name": "STAGFLATION_RISK",
            "confidence": 0.80,
            "explanation": "Growth is weak while inflation remains above the model reference.",
        }

    if growth < 0 and gap < 1.0:
        return {
            "name": "RECESSION",
            "confidence": 0.84,
            "explanation": "Real activity is contracting without a large inflation overshoot.",
        }

    if gap >= 1.25 and growth > 0.75:
        return {
            "name": "INFLATIONARY_GROWTH",
            "confidence": 0.80,
            "explanation": "Growth remains positive while inflation is materially above reference.",
        }

    if gap <= -0.75 and growth > 0:
        return {
            "name": "LOW_INFLATION_GROWTH",
            "confidence": 0.78,
            "explanation": "Real growth is positive while inflation is well below reference.",
        }

    if abs(gap) <= 0.75 and growth > 0:
        return {
            "name": "BALANCED_GROWTH",
            "confidence": 0.78,
            "explanation": "Growth is positive and inflation is relatively close to reference.",
        }

    return {
        "name": "TRANSITION",
        "confidence": 0.65,
        "explanation": "The macro mix does not fit a strong single-regime rule.",
    }


def data_confidence(data: dict[str, Observation]) -> float:
    weights = {
        "inflation_yoy": 0.28,
        "gdp_growth": 0.27,
        "policy_rate": 0.25,
        "money_growth": 0.15,
        "core_inflation": 0.05,
    }
    total = 0.0
    used = 0.0
    for metric, weight in weights.items():
        if metric in data:
            total += data[metric].effective_confidence * weight
            used += weight
    return 0.0 if used == 0 else clamp01(total / used)


def macro_asset_scores(features: dict[str, Any], confidence: float) -> dict[str, AssetResult]:
    n = features["normalized"]
    inf = n["inflation_pressure"]
    disinf = n["disinflation_pressure"]
    growth = n["growth_strength"]
    money = n["money_impulse"]
    easing = n["easing_pressure"]
    restrictive = n["restrictive_pressure"]
    real_rate = n["real_rate_strength"]

    # Scores are intentionally modest. Price valuation is a separate layer.
    raw = {
        "gold": (
            0.32 * inf
            + 0.24 * easing
            + 0.16 * money
            - 0.06 * growth
            - 0.12 * max(real_rate, 0.0)
        ),
        "foreign_currency": (
            0.22 * inf
            + 0.20 * easing
            - 0.18 * growth
            - 0.16 * max(real_rate, 0.0)
        ),
        "real_estate": (
            0.18 * inf
            + 0.25 * easing
            + 0.18 * money
            + 0.20 * growth
            - 0.22 * restrictive
        ),
        "equities": (
            0.42 * growth
            + 0.18 * money
            + 0.12 * disinf
            - 0.22 * inf
            - 0.18 * restrictive
        ),
        "government_bonds": (
            0.30 * disinf
            + 0.24 * max(real_rate, 0.0)
            - 0.30 * inf
            - 0.12 * growth
        ),
        "local_cash": (
            0.48 * max(real_rate, 0.0)
            - 0.36 * inf
            - 0.10 * money
        ),
    }

    reasons = {
        "gold": [
            "Benefits from inflation pressure and negative real-rate conditions.",
            "Can diversify monetary and geopolitical risk, but entry valuation still matters.",
        ],
        "foreign_currency": [
            "This is a local-currency diversification signal, not a forecast for one specific FX pair.",
            "Cross-country rate/inflation differentials and current FX valuation are still required.",
        ],
        "real_estate": [
            "Sensitive to real rates, credit conditions, growth and current affordability/valuation.",
        ],
        "equities": [
            "Favored by real growth and liquidity; hurt by restrictive policy and inflation pressure.",
            "Sector/company fundamentals must be evaluated separately.",
        ],
        "government_bonds": [
            "Favored by disinflation and positive real yields; hurt by persistent inflation.",
            "Duration and current yield are required for an actual bond allocation decision.",
        ],
        "local_cash": [
            "Measures purchasing-power attractiveness, not convenience or emergency liquidity value.",
        ],
    }

    out: dict[str, AssetResult] = {}
    for asset, value in raw.items():
        s = score100(value)
        out[asset] = AssetResult(
            asset=asset,
            macro_score=s,
            valuation_adjustment=0.0,
            final_score=s,
            signal=signal_label(s),
            scope="MACRO_ONLY",
            confidence=confidence,
            reasons=reasons[asset],
        )
    return out


def apply_valuation(
    assets: dict[str, AssetResult],
    market: dict[str, Any],
    inflation: Optional[float],
) -> None:
    def add(asset: str, adjustment: float, reason: str) -> None:
        item = assets[asset]
        item.valuation_adjustment += adjustment
        item.final_score = max(0.0, min(100.0, item.macro_score + item.valuation_adjustment))
        item.signal = signal_label(item.final_score)
        item.scope = "MACRO_PLUS_VALUATION"
        item.reasons.append(reason)

    if "gold_premium_pct" in market:
        premium = float(market["gold_premium_pct"])
        adj = clamp((3.0 - premium) / 15.0) * 12.0
        add("gold", adj, f"Gold premium={premium:.2f}% -> adjustment {adj:+.1f}.")

    if "equity_forward_pe" in market:
        pe = float(market["equity_forward_pe"])
        fair = float(market.get("equity_fair_pe", 16.0))
        adj = clamp((fair - pe) / max(6.0, fair * 0.45)) * 14.0
        add("equities", adj, f"Forward P/E={pe:.2f}, fair reference={fair:.2f} -> {adj:+.1f}.")

    if "housing_price_to_annual_rent" in market:
        ratio = float(market["housing_price_to_annual_rent"])
        fair = float(market.get("housing_fair_ratio", 25.0))
        adj = clamp((fair - ratio) / max(8.0, fair * 0.45)) * 12.0
        add("real_estate", adj, f"Price/annual-rent={ratio:.2f}, fair reference={fair:.2f} -> {adj:+.1f}.")

    if "government_bond_yield" in market and inflation is not None:
        y = float(market["government_bond_yield"])
        real_yield = y - inflation
        adj = clamp(real_yield / 4.0) * 14.0
        add("government_bonds", adj, f"Bond yield={y:.2f}%, real-yield proxy={real_yield:.2f}% -> {adj:+.1f}.")

    if "cash_rate" in market and inflation is not None:
        y = float(market["cash_rate"])
        real_yield = y - inflation
        adj = clamp(real_yield / 4.0) * 12.0
        add("local_cash", adj, f"Cash rate={y:.2f}%, real-rate proxy={real_yield:.2f}% -> {adj:+.1f}.")

    if "local_currency_reer_overvaluation_pct" in market:
        x = float(market["local_currency_reer_overvaluation_pct"])
        adj = clamp(x / 20.0) * 12.0
        add(
            "foreign_currency",
            adj,
            f"Local-currency REER overvaluation={x:.2f}% -> foreign-currency adjustment {adj:+.1f}.",
        )


def build_report(
    observations: dict[str, Observation],
    warnings: list[str],
    market: dict[str, Any],
) -> dict[str, Any]:
    features = macro_features(observations)
    regime = detect_regime(features)
    dconf = data_confidence(observations)
    aconf = clamp01(0.75 * dconf + 0.25 * float(regime["confidence"]))

    assets = macro_asset_scores(features, aconf)
    apply_valuation(assets, market, features["inflation_yoy"])

    ranked = sorted(
        [x.as_dict() for x in assets.values()],
        key=lambda x: x["final_score"],
        reverse=True,
    )

    if not market:
        warnings.append(
            "No market valuation JSON supplied: rankings are MACRO_ONLY, not entry-price BUY/SELL calls."
        )

    if any(x.source_kind == "seed" for x in observations.values()):
        warnings.append(
            "Seed fallback data are present. Review observation provenance before using the result."
        )

    return {
        "model": {
            "country": COUNTRY,
            "country_code": COUNTRY_CODE,
            "currency": CURRENCY,
            "central_bank": CENTRAL_BANK,
            "version": "1.0.0",
            "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "inflation_reference": INFLATION_REFERENCE,
            "inflation_reference_note": INFLATION_REFERENCE_NOTE,
            "scope": "macro regime + optional lightweight valuation",
            "disclaimer": "Research/decision-support only; not personalized financial advice.",
        },
        "regime": regime,
        "data_confidence": round(dconf, 4),
        "analysis_confidence": round(aconf, 4),
        "features": features,
        "observations": {
            k: v.as_dict() for k, v in sorted(observations.items())
        },
        "market_inputs": market,
        "assets_ranked": ranked,
        "warnings": warnings,
    }


def print_report(report: dict[str, Any]) -> None:
    f = report["features"]
    r = report["regime"]

    print("=" * 84)
    print(f"{COUNTRY} Investment Macro Model")
    print("=" * 84)
    print(f"Central bank        : {CENTRAL_BANK}")
    print(f"Currency            : {CURRENCY}")
    print(f"Regime              : {r['name']}")
    print(f"Regime confidence   : {r['confidence']:.0%}")
    print(f"Data confidence     : {report['data_confidence']:.0%}")
    print(f"Analysis confidence : {report['analysis_confidence']:.0%}")
    print(f"Reason              : {r['explanation']}")
    print()

    print("Core macro snapshot")
    print("-" * 84)
    rows = [
        ("Inflation YoY", f.get("inflation_yoy")),
        ("Core inflation", f.get("core_inflation")),
        ("Real GDP growth", f.get("gdp_growth")),
        ("Policy/reference rate", f.get("policy_rate")),
        ("Money growth", f.get("money_growth")),
        ("Inflation reference", f.get("inflation_reference")),
        ("Real-rate proxy", f.get("real_rate_proxy")),
    ]
    for name, value in rows:
        text = "N/A" if value is None else f"{value:.2f}%"
        print(f"{name:<28}: {text}")

    print()
    print("Asset ranking")
    print("-" * 84)
    print(f"{'Asset':<24} {'Macro':>9} {'ValAdj':>9} {'Final':>9} {'Signal':>21}")
    for item in report["assets_ranked"]:
        name = ASSET_LABELS.get(item["asset"], item["asset"])
        sig = SIGNAL_LABELS.get(item["signal"], item["signal"])
        print(
            f"{name:<24} "
            f"{item['macro_score']:>9.1f} "
            f"{item['valuation_adjustment']:>+9.1f} "
            f"{item['final_score']:>9.1f} "
            f"{sig:>21}"
        )

    print()
    print("Observation provenance")
    print("-" * 84)
    for metric, item in report["observations"].items():
        print(
            f"{metric:<22} {item['value']:>9.3f}  "
            f"{item['source_kind']:<20}  {item['source']}"
        )

    print()
    print("Warnings")
    print("-" * 84)
    if report["warnings"]:
        for w in report["warnings"]:
            print(f"- {w}")
    else:
        print("- None")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=f"{COUNTRY} single-file investment macro model")
    p.add_argument("--no-web", action="store_true", help="Skip live central-bank retrieval.")
    p.add_argument("--no-seed", action="store_true", help="Disable built-in seed fallback values.")
    p.add_argument("--input-json", help="Manual macro observation overrides.")
    p.add_argument("--market-json", help="Optional market valuation inputs.")
    p.add_argument("--output", help="Save full report JSON to this file.")
    p.add_argument("--json", action="store_true", help="Print JSON instead of human report.")
    p.add_argument("--debug", action="store_true", help="Print network/debug messages to stderr.")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    try:
        manual = load_json(args.input_json)
        market = load_json(args.market_json)
    except Exception as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2

    live: dict[str, Observation] = {}
    warnings: list[str] = []

    if not args.no_web:
        try:
            live, live_warnings = fetch_live(HttpClient(debug=args.debug))
            warnings.extend(live_warnings)
        except Exception as exc:
            warnings.append(f"Live retrieval failed: {type(exc).__name__}: {exc}")

    try:
        observations, merge_warnings = merge_observations(
            live=live,
            manual=manual,
            use_seed=not args.no_seed,
        )
        warnings.extend(merge_warnings)
    except Exception as exc:
        print(f"Merge error: {exc}", file=sys.stderr)
        return 2

    report = build_report(observations, warnings, market)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_report(report)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
