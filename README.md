# SFP Reversion — FX Mean-Reversion Algorithmic Trading System

Systematic version of a discretionary FX strategy: fade key support/resistance levels,
confirmed by Swing Failure Patterns (SFP) and MACD divergence. Daily chart decides
*where* (levels, trend bias); hourly chart decides *when* (touches, triggers, entries).
Price data: TradingView feed (OANDA venue).

Core thesis: levels tested fewer times reverse more reliably than exhausted ones.
Touch count grades the setup; retest count gates the confirmation; both gates must pass.

## Pipeline

```
TradingView feed → cache → daily levels → hourly touch/retest tracking
  → confluence votes (D1 bias, fib, ATR stretch) → SFP / MACD confirmation
  → decision tree (orders: limit/stop/target) → backtest engine
  → falsification gate → walk-forward / significance / sensitivity → reports
```

No lookahead anywhere: every output at bar `t` uses only data available at or before
`t` (plus a truncation-invariance test proving it). ATR regimes are measured through
the prior bar so violent bars never set their own hurdles.

## Project structure

```
config.yaml                  # every tunable number (strategy never hardcodes)
plan.md                      # strategy spec + phased build plan (source of truth)
src/sfp_reversion/
  config.py                  # typed config reader
  data/                      # OHLC schema (the contract) + TradingView loader + parquet cache
  levels/                    # swing detection, level clustering, touch/retest timelines
  confluence/                # d1_bias, fib_levels, atr_extension
  confirmation/              # sfp, macd_divergence
  signals/                   # decision_tree: daily levels + hourly entries → orders
  backtest/                  # limit fills, stop-first exits, costs, 1%-risk sizing
  validation/                # random_baseline, walk_forward, significance, sensitivity
  report/                    # metrics table + equity-curve plot
  cli.py                     # fetch / signals / backtest / validate
tests/                       # 85+ checks, one file per module
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
uv run sfp-reversion validate EUR_USD --parameter touch_tolerance_atr --values 0.05 0.1 0.15 0.2
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
never code. Key sections: `levels` (swings, tolerance, exhaustion), `confluence`,
`confirmation` (SFP, MACD), `signal` (gates, reward:risk, stops/targets),
`backtest` (costs, risk %), `validation` (windows, trials).

## Current status (honest)

End-to-end system complete and verified: 85+ tests green, falsification gate passes
(random entries show no edge → engine is honest), truncation probe passes.
On ~2y EUR/USD hourly at plan defaults: 27 signals → 8 trades. Money numbers are
noise-scale — the gates as written are highly selective (SFP + min-reward-risk bind
hardest). No edge claimed; the system correctly reports insufficient evidence.

## Roadmap

1. **Volume** — hourly data for 3–4 majors; full daily history for levels.
2. **Tuning** — loosen the gate stack (SFP thresholds, confluence counts, RR
   minimum, level density) until frequency is sane; each setting judged by
   walk-forward out-of-sample, never by in-sample looks.
3. **Edge proof** — dozens-to-hundreds of trades, Sharpe CI above zero, deflated
   Sharpe surviving trial counts, sensitivity showing hills not spikes.
4. **Paper trading** — live prices, fake money, weeks of proving live matches backtest.
5. **Execution layer** — broker API connection (Kenya-compatible: Exness / IC Markets /
   Interactive Brokers), order placement, position sync, broker-feed data.
6. **Risk guardrails** — kill switch, max daily loss, exposure caps, reconnect handling,
   alerting. No real capital before these exist.
7. **Live** — small size first, scale only with continued out-of-sample proof.
