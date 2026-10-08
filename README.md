# SFP Reversion — FX Swing-Failure Algorithmic Trading System

Systematic version of Trader Dante's Setup A: fade the first clean failed break
of an obvious daily support/resistance level (wick beyond, body closes back
inside → Swing Failure Pattern on H1). Daily decides *where*; hourly decides
*when*. Price data: TradingView feed (OANDA venue).

Core thesis: an obvious level's first clean failure traps breakout chasers and
reverses; chewed-through levels and messy shelves are skipped, not faded.

## Pipeline

```
TradingView feed → cache → daily levels (fractal swings, clustered)
  → H1 SFP scan (sweep + close + origin-wick + min-R filters, break-death)
  → market orders (entry/stop/target) → backtest engine (next-open fills,
     stop-first exits, warning-sign exit, costs, 1%-risk sizing)
  → falsification gate → walk-forward / significance / sensitivity → reports
```

No lookahead anywhere: every output at bar `t` uses only data available at or before
`t` (plus a truncation-invariance test proving it). ATR regimes are measured through
the prior bar so violent bars never set their own hurdles.

## Project structure

```
config.yaml                  # every tunable number (strategy never hardcodes)
philosophy.md                # background + principles (why)
strategy.md                  # Setup A (SFP) spec — the tradable rules
src/sfp_reversion/
  config.py                  # typed config reader
  data/                      # OHLC schema (the contract) + TradingView loader + parquet cache
  levels/                    # fractal swings, clustered levels, origin-wick tracking
  confirmation/              # SFP trigger (sweep + close back inside)
  signals/                   # sfp: daily levels + H1 SFP → market orders
  backtest/                  # next-open fills, stop-first exits, warning exit, costs, 1%-risk sizing
  validation/                # random_baseline, walk_forward, significance, sensitivity
  report/                    # metrics table + equity-curve plot
  cli.py                     # fetch / signals / backtest / validate / portfolio
tests/                       # one file per module (Setup A only)
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
```

Any TradingView-covered pair works (`EUR_USD`, `GBP_USD`, `USD_JPY`, …); add odd symbols
to `data.tradingview.symbols` in `config.yaml`. Each pair/timeframe caches separately.

## Test

```bash
uv run pytest                        # full suite (~2.5 min)
uv run pytest tests/test_sfp.py -v    # one module
uvx ruff check src tests              # lint
uvx ruff format --check src tests     # formatting
```

## Research notebooks

```bash
uv run jupyter lab                # open notebooks/explore.ipynb
```

Price + levels + signals + trades on one chart, parameterized by pair and dates.
Notebooks import the same modules as the CLI — exploration here, verdicts there.

## Configuration

All strategy numbers live in `config.yaml` and are read at runtime — tune config,
never code. Key sections: `levels` (swings, clustering, break tolerance),
`sfp` (wick/close/origin filters, stop buffer, fallback target, min-R),
`backtest` (costs, risk %, max hold), `validation` (windows, trials).

## Current status (honest)

End-to-end Setup A system complete and verified: 70 tests green, falsification
gate passes (random entries show no edge → engine is honest).
On ~2y EUR/USD hourly at defaults: 7 signals → 7 trades, net −315 (2/7 wins).
Noise-scale — no edge claimed; the system correctly reports insufficient
evidence. Frequency is the binding constraint: most daily levels are either
long dead or never swept on H1 before they break.

## Roadmap

1. **Volume** — hourly data for 3–4 majors; full daily history for levels.
2. **Tuning** — sweep SFP fractions, origin-wick cap, RR minimum (strategy.md §9
   experiments in order); each setting judged by walk-forward out-of-sample,
   never by in-sample looks.
3. **Edge proof** — dozens-to-hundreds of trades, Sharpe CI above zero, deflated
   Sharpe surviving trial counts, sensitivity showing hills not spikes.
4. **Paper trading** — live prices, fake money, weeks of proving live matches backtest.
5. **Execution layer** — broker API connection (Kenya-compatible: Exness / IC Markets /
   Interactive Brokers), order placement, position sync, broker-feed data.
6. **Risk guardrails** — kill switch, max daily loss, exposure caps, reconnect handling,
   alerting. No real capital before these exist.
7. **Live** — small size first, scale only with continued out-of-sample proof.
