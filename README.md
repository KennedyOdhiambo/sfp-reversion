# SFP Reversion — FX Swing-Failure Backtesting System

Systematic implementation of a swing-failure mean-reversion strategy: fade the
first clean failed break of an obvious daily support/resistance level (wick
beyond, body closes back inside → Swing Failure Pattern on H1). Daily decides
*where*; hourly decides *when*. Price data: TradingView websocket feed (OANDA
venue), scraped directly with history paging.

Core thesis: an obvious level's first clean failure traps breakout chasers and
reverses; chewed-through levels and messy shelves are skipped, not faded.

## Pipeline

```
TradingView feed → cache → daily levels (fractal swings, clustered)
  → H1 SFP scan (sweep + close + origin-wick + min-R filters, break-death)
  → orders (market/limit, stop, target) → backtest engine (fills with expiry,
     stop-first exits, warning-sign exit, costs w/ per-pair pips, 1%-risk sizing)
  → falsification gate → walk-forward / significance / sensitivity → reports
```

No lookahead anywhere: every output at bar `t` uses only data available at or before
`t`. ATR regimes are measured through the prior bar so violent bars never set their
own hurdles.

## Project structure

```
config.yaml                  # every tunable number (strategy never hardcodes)
philosophy.md                # background + principles (why)
src/sfp_reversion/
  config.py                  # typed config reader
  data/                      # OHLC schema + own TV websocket scraper + parquet cache
  levels/                    # fractal swings, clustered levels, quality filters
  confirmation/              # SFP trigger (sweep + close back inside)
  signals/                   # sfp: daily levels + H1 SFP → orders
  backtest/                  # fills w/ expiry, stop-first exits, warning exit, costs, sizing
  validation/                # random_baseline, walk_forward, significance, sensitivity
  report/                    # metrics table + equity-curve plot
  cli.py                     # fetch / signals / backtest / validate / portfolio
tests/                       # one file per module
data/cache/                  # local parquet (ignored by git, re-fetchable)
reports/                     # generated plots (ignored by git)
```

## Setup

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --extra dev     # install runtime + dev deps (pytest, ruff)
```

## Run

```bash
# pull data (daily + hourly; re-runs only fetch what's new)
uv run sfp-reversion fetch EUR_USD
uv run sfp-reversion fetch EUR_USD --granularity H1 --start 2025-01-01 --end 2025-12-31

# generate signals (full history behind the scenes; bounds filter the window)
uv run sfp-reversion signals EUR_USD --start 2025-01-01 --end 2025-06-30 --out signals.csv

# backtest + falsification gate + equity plot
uv run sfp-reversion backtest EUR_USD --start 2025-01-01 --end 2025-12-31

# walk-forward, or sweep one parameter (robust vs knife-edge verdict)
uv run sfp-reversion validate EUR_USD --start 2025-01-01 --end 2025-12-31
uv run sfp-reversion validate EUR_USD --parameter wick_atr --values 0.05 0.1 0.15 0.2

# whole universe at once
uv run sfp-reversion portfolio
```

Any TradingView-covered pair works (`EUR_USD`, `GBP_USD`, `USD_JPY`, …); add odd symbols
to `data.tradingview.symbols` in `config.yaml`. Each pair/timeframe caches separately.

## Test

```bash
uv run pytest                        # full suite
uv run pytest tests/test_sfp.py -v    # one module
uvx ruff check src tests              # lint
uvx ruff format --check src tests     # formatting
```

## Configuration

All strategy numbers live in `config.yaml` and are read at runtime — tune config,
never code. Key sections: `levels` (swings, clustering, break tolerance, quality),
`sfp` (wick/close/origin filters, stop buffer, fallback target, min-R, min-stop,
5m refinement), `backtest` (costs incl. per-pair pips and exit slippage, risk %,
max hold), `validation` (windows, trials).

## Current status (honest)

End-to-end system complete and verified: 82 tests green, falsification gate passes
on every pair (random entries show no edge → engine is honest).
On 11 pairs, Jan 2025 → now: 170 trades, −19%, profit factor 0.85,
Sharpe −0.38 with a confidence interval fully below zero. No edge claimed; the
system correctly reports insufficient evidence and the setup is parked.
