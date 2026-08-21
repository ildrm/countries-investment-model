# Countries Investment Model

**A Python-based macroeconomic investment analysis framework for comparing asset attractiveness across countries using central-bank data, economic regime detection, monetary-policy analysis, inflation, growth, liquidity, interest rates, and optional market valuation inputs.**

The project converts official macroeconomic data into a structured investment-analysis pipeline that evaluates economic conditions and ranks major asset classes such as **equities, government bonds, gold, foreign currencies, real estate, fixed income, and cash**.

Each country is implemented as an independent Python file with country-specific data sources, normalization parameters, monetary-policy assumptions, economic-regime rules, and asset-scoring logic.

> **Important:** This project is intended for economic research, quantitative analysis, and decision support. It does not provide personalized financial advice and should not be treated as a standalone BUY/SELL system.

---

## Supported Countries

| Country             | File                | Main Monetary / Economic Source  |
| ------------------- | ------------------- | -------------------------------- |
| 🇮🇷 Iran           | `iran.py`           | Central Bank of Iran             |
| 🇺🇸 United States  | `united_states.py`  | Federal Reserve / FRED           |
| 🇨🇳 China          | `china.py`          | People's Bank of China           |
| 🇩🇪 Germany        | `germany.py`        | Deutsche Bundesbank / Eurosystem |
| 🇯🇵 Japan          | `japan.py`          | Bank of Japan                    |
| 🇬🇧 United Kingdom | `united_kingdom.py` | Bank of England                  |

Additional countries can be added using the same architecture.

---

## What This Project Does

The model follows a multi-stage macroeconomic investment-analysis pipeline:

```text
Official Economic Data
        |
        v
Raw Observations
        |
        v
Data Quality / Confidence
        |
        v
Staleness Analysis
        |
        v
Normalized Macro Indicators
        |
        v
Economic Regime Detection
        |
        v
Asset-Class Macro Scoring
        |
        v
Optional Market Valuation
        |
        v
Final Asset Ranking
```

Instead of trying to predict an exact future price, the system asks a more useful question:

> Given the current macroeconomic environment of a country, which asset classes are structurally more or less attractive?

---

## Core Economic Inputs

Depending on data availability for each country, the models analyze indicators such as:

### Inflation

* Headline CPI
* Core inflation
* Year-over-year inflation
* Monthly inflation
* Inflation trend
* Inflation pressure relative to the central-bank target or model reference

### Economic Growth

* Real GDP growth
* Quarterly economic growth
* Annual growth
* Growth forecasts
* Economic expansion or contraction

### Monetary Policy

* Central-bank policy rate
* Interbank rates
* Repo / reverse-repo rates
* Interest-rate corridors
* Effective policy-rate proxies
* Real interest-rate conditions

### Monetary Conditions

* Money supply
* M2 growth
* Liquidity growth
* Monetary-base growth
* Monetary expansion or contraction

### Additional Country-Specific Indicators

Some country models may also use or support:

* Current-account conditions
* Exchange-rate pressure
* credit conditions
* monetary-policy forecasts
* central-bank outlook reports
* official economic projections
* country-specific liquidity indicators
* auxiliary official macroeconomic statistics

---

## Economic Regime Detection

The project classifies macroeconomic conditions into regimes instead of treating every economic environment the same way.

Possible regimes include:

```text
BALANCED_GROWTH
LOW_INFLATION_GROWTH
INFLATIONARY_GROWTH
STAGFLATION
STAGFLATION_RISK
RECESSION
TRANSITION
```

The Iran model also supports a more specific high-inflation monetary regime:

```text
STAGFLATION_DEBASEMENT
```

Economic regimes matter because the same asset can behave very differently under different combinations of:

```text
Inflation
Growth
Interest Rates
Liquidity
Real Rates
Monetary Expansion
```

For example, high inflation combined with strong growth is economically different from high inflation combined with recession.

---

## Asset Classes

The models currently evaluate the macroeconomic attractiveness of major asset classes including:

| Asset                           | Economic Role                                    |
| ------------------------------- | ------------------------------------------------ |
| Gold                            | Inflation, monetary and risk hedge               |
| Foreign Currency                | Local-currency diversification                   |
| Equities                        | Exposure to growth, earnings and liquidity       |
| Government Bonds / Fixed Income | Yield, duration and disinflation exposure        |
| Real Estate                     | Real-asset and inflation exposure                |
| Local Cash                      | Liquidity and real purchasing-power preservation |

The Iran model uses terminology adapted to the Iranian financial system, while the other models use a more generalized international asset structure.

---

## Macro Score vs. Investment Recommendation

This distinction is fundamental to the project.

A high macro score does **not** automatically mean:

```text
BUY
```

It means:

```text
The current macroeconomic environment is supportive of this asset class.
```

The asset itself may still be overvalued.

For example:

```text
Gold Macro Environment     = Strong Positive
Gold Market Valuation      = Very Expensive
Final Investment Decision  = Not necessarily a BUY
```

This is why the framework separates:

```text
Macro Analysis
```

from:

```text
Market Valuation
```

---

## Scoring Model

At a simplified level, each asset receives a macroeconomic score derived from normalized economic factors.

Conceptually:

```text
Macro Score =
    Inflation Effect
  + Growth Effect
  + Monetary Liquidity Effect
  + Interest Rate Effect
  + Real Rate Effect
  + Country-Specific Effects
```

The score is normalized to:

```text
0 - 100
```

Example interpretation:

|  Score | Signal          |
| -----: | --------------- |
| 75–100 | Strong Positive |
|  60–74 | Positive        |
|  45–59 | Neutral         |
|  30–44 | Weak            |
|   0–29 | Very Weak       |

The exact economic weights are country-aware and may differ between models.

---

## Why Country-Specific Models?

A major design principle of this project is:

> Economic variables should not be interpreted identically across all countries.

For example:

* 5% money growth means something very different in China and Iran.
* A 2% inflation rate has different implications in Japan and an emerging market.
* Germany does not operate an independent national monetary policy because it participates in the Eurosystem.
* China's monetary-policy framework cannot be modeled exactly like the Federal Reserve.
* Japan has historically operated under a structurally different interest-rate environment.
* Currency-debasement risk is much more important in some economies than others.

Therefore, every country file contains its own:

```text
Inflation reference
Growth normalization
Money-growth normalization
Policy-rate interpretation
Economic data retrieval logic
Country-specific assumptions
```

---

## Data Sources

The framework prioritizes official central-bank and central-bank-hosted economic information.

### Iran

Primary source:

```text
Central Bank of the Islamic Republic of Iran
```

The Iran model analyzes data such as:

```text
Inflation
Liquidity growth
Monetary-base growth
GDP growth
Interbank rates
Policy rates
```

---

### United States

Primary sources:

```text
Board of Governors of the Federal Reserve System
Federal Reserve Bank of St. Louis / FRED
```

Series may include:

```text
CPI
Core CPI
M2
Effective Federal Funds Rate
Real GDP
```

---

### China

Primary source:

```text
People's Bank of China
```

The model may analyze:

```text
7-day reverse repo rate
M2 growth
Loan Prime Rate
Monetary-policy publications
```

Where necessary, official auxiliary macroeconomic series may be used for indicators that are not directly produced by the PBOC.

---

### Germany

Primary sources:

```text
Deutsche Bundesbank
Eurosystem
```

Germany requires special treatment because monetary policy is determined within the Eurosystem rather than by an independent German policy rate.

The model can analyze:

```text
German HICP
Core inflation
GDP outlook
ECB / Eurosystem policy rates
```

---

### Japan

Primary source:

```text
Bank of Japan
```

The model supports analysis of:

```text
Policy rates
Monetary Policy Statements
Outlook Reports
Inflation projections
GDP projections
Money stock
```

Some Bank of Japan data are published in PDF documents, so optional PDF parsing is supported.

---

### United Kingdom

Primary source:

```text
Bank of England
```

The model analyzes information such as:

```text
Bank Rate
CPI inflation
GDP projections
Monetary Policy Reports
Monetary-policy decisions
```

---

## Data Provenance

Every observation retains metadata describing where it came from.

A typical observation contains:

```json
{
  "metric": "inflation_yoy",
  "value": 2.8,
  "unit": "percent",
  "period": "2026-07",
  "release_date": "2026-08-19",
  "frequency": "monthly",
  "source": "Central Bank / Official Source",
  "source_url": "...",
  "source_kind": "live_central_bank",
  "base_confidence": 0.97
}
```

This makes the analysis auditable.

The system can distinguish between:

```text
live_central_bank
official_auxiliary
manual
seed
```

---

## Data Priority

When multiple values exist for the same indicator, the project follows this precedence:

```text
Manual Override
      >
Live Official Data
      >
Built-in Seed Snapshot
```

In other words:

```text
manual > live > seed
```

Seed values exist so the model can still run when:

* a central-bank website is temporarily unavailable,
* an HTML structure changes,
* a PDF cannot be parsed,
* a network connection fails,
* a data release has not yet been scraped successfully.

Seed observations are clearly identified in the output.

---

## Confidence and Data Staleness

Economic data have different publication frequencies.

For example:

```text
Policy Rate    -> event / daily
Interbank Rate -> daily / weekly
Inflation      -> monthly
GDP            -> quarterly
Forecasts      -> quarterly / periodic
```

An old daily interest-rate observation should lose relevance much faster than an annual macroeconomic statistic.

Therefore each observation receives a:

```text
Base Confidence
```

and a:

```text
Staleness Factor
```

which are combined into:

```text
Effective Confidence
```

Conceptually:

```text
Effective Confidence =
    Base Confidence
    x
    Staleness Adjustment
```

The model then produces:

```text
Data Confidence
Regime Confidence
Analysis Confidence
```

This prevents stale or low-quality data from silently being treated as equally reliable as fresh official observations.

---

# Installation

## Requirements

Recommended:

```text
Python 3.10+
```

Install the common dependencies:

```bash
py -m pip install requests beautifulsoup4
```

On Linux or macOS:

```bash
python3 -m pip install requests beautifulsoup4
```

---

## Optional Dependencies

### Iran

For more resilient browser-based extraction and spreadsheet support:

```bash
py -m pip install playwright openpyxl
py -m playwright install chromium
```

### Japan / China

For parsing some official PDF releases:

```bash
py -m pip install pypdf
```

---

# Usage

Each country model is independent.

## Iran

```bash
py iran.py
```

## United States

```bash
py united_states.py
```

## China

```bash
py china.py
```

## Germany

```bash
py germany.py
```

## Japan

```bash
py japan.py
```

## United Kingdom

```bash
py united_kingdom.py
```

On Linux or macOS, replace:

```text
py
```

with:

```text
python3
```

---

# CLI Options

The country models expose a consistent command-line interface.

### Run with live data

```bash
py united_states.py
```

### Run offline

```bash
py united_states.py --no-web
```

This skips live requests and uses available seed/manual data.

### Disable seed fallback

```bash
py united_states.py --no-seed
```

### Print JSON

```bash
py united_states.py --json
```

### Save a JSON report

```bash
py united_states.py --output report.json
```

### Override macroeconomic data

```bash
py united_states.py --input-json macro.json
```

### Supply market valuation information

```bash
py united_states.py --market-json market.json
```

### Enable debugging

```bash
py united_states.py --debug
```

Options can also be combined:

```bash
py united_states.py \
  --input-json macro.json \
  --market-json market.json \
  --output report.json
```

---

# Manual Macro Overrides

You can override official or seed observations without modifying the Python source code.

Example `macro.json`:

```json
{
  "inflation_yoy": 2.7,
  "core_inflation": 2.9,
  "gdp_growth": 1.8,
  "policy_rate": 3.5,
  "money_growth": 4.7
}
```

More detailed metadata can also be supplied:

```json
{
  "inflation_yoy": {
    "value": 2.7,
    "unit": "percent",
    "period": "2026-07",
    "release_date": "2026-08-15",
    "frequency": "monthly",
    "source": "Manual verified observation",
    "base_confidence": 0.98
  }
}
```

Manual values take precedence over live and seed observations.

---

# Optional Market Valuation Layer

Macroeconomic conditions alone cannot determine whether an asset is currently cheap or expensive.

Optional market inputs allow the model to modify the macro score.

Example `market.json`:

```json
{
  "gold_premium_pct": 2.0,
  "equity_forward_pe": 17.0,
  "housing_price_to_annual_rent": 22.0,
  "government_bond_yield": 4.0,
  "cash_rate": 3.5,
  "local_currency_reer_overvaluation_pct": 5.0
}
```

Depending on the country model, supported valuation inputs may include:

```text
Gold premium
Equity P/E
Housing price-to-rent ratio
Government bond yield
Cash / deposit rate
Currency REER valuation
```

When valuation data are available:

```text
Final Score =
    Macro Score
    +
    Valuation Adjustment
```

Without valuation data, the output is explicitly labeled:

```text
MACRO_ONLY
```

---

# Example Output

An illustrative terminal result may look like:

```text
====================================================================================
Country Investment Macro Model
====================================================================================
Central bank        : Central Bank
Currency            : LOCAL
Regime              : BALANCED_GROWTH
Regime confidence   : 78%
Data confidence     : 91%
Analysis confidence : 88%

Core macro snapshot
------------------------------------------------------------------------------------
Inflation YoY               : 2.60%
Core inflation              : 2.80%
Real GDP growth             : 1.20%
Policy/reference rate       : 3.50%
Money growth                : 4.70%
Inflation reference         : 2.00%
Real-rate proxy             : 0.90%

Asset ranking
------------------------------------------------------------------------------------
Asset                       Macro    ValAdj     Final                Signal
Equities                     63.5       +0.0      63.5              Positive
Government Bonds             59.8       +0.0      59.8               Neutral
Real Estate                  55.1       +0.0      55.1               Neutral
Local Cash                   52.9       +0.0      52.9               Neutral
Gold                         44.7       +0.0      44.7                  Weak
Foreign Currency             41.8       +0.0      41.8                  Weak
```

The values above are illustrative and are not current investment recommendations.

---

# JSON Report Structure

Using:

```bash
py japan.py --json
```

or:

```bash
py japan.py --output japan_report.json
```

produces a structured report containing:

```text
model
regime
data_confidence
analysis_confidence
features
observations
market_inputs
assets_ranked
warnings
```

Example:

```json
{
  "model": {
    "country": "Japan",
    "country_code": "JP",
    "currency": "JPY",
    "central_bank": "Bank of Japan (BOJ)",
    "version": "1.0.0"
  },
  "regime": {
    "name": "BALANCED_GROWTH",
    "confidence": 0.78
  },
  "data_confidence": 0.91,
  "analysis_confidence": 0.88,
  "assets_ranked": []
}
```

This makes the project suitable for integration with:

```text
Dashboards
REST APIs
Databases
Backtesting systems
Data pipelines
Portfolio research tools
Jupyter notebooks
Scheduled economic analysis
Quantitative research systems
```

---

# Repository Structure

```text
countries-investment-model/
|
|-- iran.py
|-- united_states.py
|-- china.py
|-- germany.py
|-- japan.py
|-- united_kingdom.py
|
|-- README.md
`-- LICENSE
```

Each country intentionally remains self-contained.

This makes it possible to:

* run a country independently,
* copy a model without installing the entire project,
* customize normalization rules country by country,
* experiment with country-specific indicators,
* add new countries incrementally.

---

# Design Principles

## 1. Official Data First

Central-bank and official economic data are preferred over third-party aggregators whenever practical.

---

## 2. Preserve Raw Information

Official observations should not be silently modified.

Instead of changing a reported number, the framework keeps:

```text
Raw Value
Source
Period
Release Date
Confidence
Staleness
```

separately from derived economic signals.

---

## 3. Do Not Treat Official Data as Absolute Truth

An official observation is treated as:

```text
An official input
```

not automatically:

```text
The complete economic reality
```

Confidence, staleness, alternative official statistics, and market-based data can be used to evaluate the reliability of the overall signal.

This is especially important for countries where:

* statistics may be revised,
* publication is delayed,
* alternative exchange rates exist,
* price controls distort market signals,
* capital controls exist,
* official and market prices diverge.

---

## 4. Macro Analysis Is Not Market Timing

A favorable economic environment for an asset does not mean the asset should be purchased at any price.

The framework deliberately separates:

```text
Macroeconomic Attractiveness
```

from:

```text
Market Valuation
```

---

## 5. Explainability Before Complexity

The current model is intentionally rule-based and interpretable.

The goal is to understand:

```text
Why did the model classify this regime?
Why did gold receive this score?
Why did equities lose points?
Why are bonds attractive?
```

before introducing more complex statistical or machine-learning models.

---

# Current Model Architecture

The project currently represents approximately:

```text
Version 1
Rule-Based Macroeconomic Model
```

A natural evolution of the project is:

```text
V1
Rule-Based Economic Regime Detection
        |
        v
V2
Statistical Calibration
        |
        v
V3
Historical Backtesting
        |
        v
V4
Probabilistic / Bayesian Regime Detection
        |
        v
V5
Machine-Learning-Assisted Forecasting
        |
        v
V6
Portfolio Optimization
```

The intention is not to replace economic reasoning with machine learning, but to use statistical models to test, calibrate, and improve economic assumptions.

---

# Planned Improvements

Potential future development includes:

* historical macroeconomic database,
* automated historical backtesting,
* country-to-country comparison,
* standardized cross-country scores,
* yield-curve analysis,
* sovereign-risk modeling,
* currency valuation models,
* current-account analysis,
* credit-growth indicators,
* unemployment and labor-market indicators,
* fiscal-policy analysis,
* commodity exposure,
* energy dependence,
* geopolitical-risk layer,
* political-risk layer,
* equity-sector analysis,
* company-level fundamental scoring,
* bond duration analysis,
* housing affordability models,
* commodity models,
* global liquidity indicators,
* correlation matrices,
* Monte Carlo simulation,
* Bayesian economic-regime detection,
* Hidden Markov Models,
* portfolio optimization,
* risk-adjusted asset allocation,
* historical drawdown analysis,
* web dashboard,
* REST API,
* scheduled data updates,
* automatic anomaly detection,
* country-ranking engine.

---

# Adding a New Country

The preferred approach is to create a standalone file:

```text
canada.py
australia.py
turkey.py
india.py
brazil.py
...
```

A country model should define:

```text
Country
Country code
Currency
Central bank
Official data sources
Inflation reference
Growth normalization
Money-growth normalization
Seed snapshot
Live-data fetcher
Regime detection inputs
Asset valuation references
```

The command-line interface should remain consistent:

```bash
py country.py
py country.py --no-web
py country.py --output report.json
py country.py --input-json macro.json
py country.py --market-json market.json
```

---

# Backtesting

A macroeconomic investment model should not be trusted merely because its rules appear economically reasonable.

The intended validation method is historical backtesting.

For each country, future versions should evaluate:

```text
Economic data available at time T
        |
        v
Detected regime at time T
        |
        v
Asset scores at time T
        |
        v
Actual asset returns over T + N months
```

Important considerations include:

* publication delays,
* revised economic data,
* look-ahead bias,
* survivorship bias,
* transaction costs,
* taxes,
* inflation,
* currency conversion,
* drawdowns,
* volatility,
* regime transition timing.

The objective is to test whether the model identifies **relative asset attractiveness**, not whether it predicts every market movement.

---

# What This Project Is Not

This project is **not**:

```text
A trading bot
A guaranteed return system
A financial adviser
A high-frequency trading system
An AI stock picker
A cryptocurrency signal service
A replacement for fundamental analysis
A replacement for risk management
```

It is a:

```text
Macroeconomic Investment Decision-Support Framework
```

---

# Risk Warning

Financial markets are uncertain.

Economic relationships change over time and historical relationships may fail in future regimes.

Central-bank data can be:

* revised,
* delayed,
* incomplete,
* estimated,
* subject to methodological changes.

Market prices may also already reflect expected economic developments before official statistics are published.

Use this project for:

```text
Research
Education
Economic analysis
Quantitative experimentation
Backtesting
Decision support
```

Do not use a single model output as the sole basis for a financial decision.

---

# SEO / Project Keywords

This repository focuses on:

```text
investment analysis
macroeconomics
quantitative finance
asset allocation
central bank data
economic indicators
economic regime detection
monetary policy
inflation analysis
interest rates
portfolio management
financial analysis
country analysis
economic data
risk analysis
fundamental analysis
Python finance
investment model
global macro
cross-country investment analysis
```

---

# Contributing

Contributions are welcome.

Useful contribution areas include:

* adding new countries,
* improving official-data extraction,
* replacing seed data with reliable live sources,
* adding macroeconomic indicators,
* improving regime detection,
* developing historical backtests,
* validating scoring weights,
* adding market valuation models,
* improving documentation,
* adding automated tests.

When contributing a new country, prefer official central-bank or official statistical sources and preserve full observation provenance.

---

# License

This project is released under the **MIT License**.

See the `LICENSE` file for details.

---

# Disclaimer

This software is provided for educational, research, and analytical purposes only.

Nothing in this repository constitutes:

* investment advice,
* financial advice,
* trading advice,
* legal advice,
* tax advice,
* an offer to buy or sell securities or financial instruments.

All investment decisions involve risk, including the possible loss of principal.

Always independently verify economic data and perform appropriate financial and risk analysis before making investment decisions.

---

## Summary

**Countries Investment Model** is an open-source Python framework for converting central-bank and macroeconomic data into explainable economic-regime classifications and cross-asset investment signals.

The core idea is simple:

```text
Understand the economy
        +
Understand the monetary regime
        +
Measure data quality
        +
Evaluate asset sensitivity
        +
Consider valuation
        =
Better structured investment decisions
```

The project is designed to evolve from an interpretable rule-based model into a historically tested, probabilistic, multi-country asset-allocation framework.
