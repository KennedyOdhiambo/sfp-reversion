# FX Level/SFP Mean-Reversion Strategy

## Status: Draft v0.1 — several definitions need precision before implementation (see "Open Questions" per module)

---

## 1. Strategy Overview

A discretionary-turned-systematic FX strategy trading mean reversion off key support/resistance
levels, with entry confirmation via Swing Failure Pattern (SFP) and, in weaker setups, MACD
divergence. Originally traded manually 2022–2023 across multiple pairs with a daily macro-bias +
execution-level journaling process. This document formalizes the decision tree into implementable
rules.

Core thesis: price approaching a level with **fewer prior touches and fewer retests** is a
higher-probability reversal setup than a level that has been tested repeatedly (exhaustion). The
system grades signal quality by touch count and retest count, gating weaker setups behind
additional confirmation (confluence factors, SFP, MACD divergence) and rejecting exhausted levels
outright.

---

## 2. Definitions

Each of these needs a **precise, coded definition** before implementation. Current best
understanding below; items marked `[CONFIRM]` need sign-off before coding, since an imprecise
definition here corrupts every downstream signal.

### 2.1 Level
A significant support/resistance price point. `[CONFIRM]` detection method — candidates:
- Swing high/low (local extrema over N bars)
- Prior day/week high-low
- Round numbers / psychological levels
- Some combination, weighted

### 2.2 Inverse Level
The opposing S/R level (e.g. if trading off resistance, the corresponding support). Used as a
cross-check per the flowchart — exact role in the decision `[CONFIRM]` (informational context vs.
hard filter).

### 2.3 Touch
An approach of price to a level without a full retest/breakout event. `[CONFIRM]` tolerance
(fixed pips vs. ATR-scaled) and what distinguishes a "touch" from a "retest" — the flowchart
treats these as two separate counters, not one.

### 2.4 Retest
A touch occurring *after* the level has already been established/traded off once.
`[CONFIRM]` — does the first touch that defines the level count toward the retest counter, or
does counting start only after?

### 2.5 Confluence Factors
Used to gate entries on weaker (fewer-touch) setups:
- **D1 Bias** — daily directional bias. `[CONFIRM]` calculation (trend filter, EMA-based, discretionary macro read as in journal, or a combination)
- **Fib Level** — level coincides with a Fibonacci retracement/extension of daily swings.
  `[CONFIRM]` which swing points define the fib, which ratios count
- **Level at or past ATR** — level sits at or beyond an ATR-based extension from some reference
  point. `[CONFIRM]` reference point and ATR period/multiple

### 2.6 SFP (Swing Failure Pattern)
Price wicks beyond the level, then closes back inside it — a liquidity sweep signaling
exhaustion of the breakout attempt. `[CONFIRM]`:
- Minimum wick distance beyond level (fixed pips / ATR fraction)
- How "solidly" the close must be back inside (e.g. close must clear the level by X, not just
  barely inside)

### 2.7 MACD Divergence (over prior 3 lows/highs)
Standard MACD divergence, scoped specifically to the prior 3 swing lows (for bullish) or highs
(for bearish). `[CONFIRM]` MACD parameters (12/26/9 standard, or custom) and exact divergence
detection logic (price vs. MACD histogram or MACD line).

### 2.8 Thrust Candle
The candle that "confirms" the level / triggers stop placement. `[CONFIRM]` — is this the
candle that formed the SFP wick, or a separate momentum/impulse candle definition (size
threshold relative to ATR, engulfing, etc.)?

### 2.9 FTA (First Target Area)
Take-profit target. `[CONFIRM]` calculation — likely the next opposing S/R level, but needs
precise identification logic matching section 2.1's level detection.

---

## 3. Decision Tree (as specified)

```
Determine level relationship:
  Sell setup: level is ABOVE current market
  Buy setup:  level is BELOW current market

Check Inverse Level (cross-reference opposing S/R)
  → informs Number of Touches branch

NUMBER OF TOUCHES on the level:
  3+ touches → Limit order at level
               Stop beyond thrust candle
               Target at FTA
               (highest confidence — no extra confluence required)

  2 touches  → Limit order at level
               Requires 1 confluence factor
               Stop beyond thrust candle
               Target at FTA

  1 touch    → Limit order at level
               Requires 2 confluence factors
               Stop beyond thrust candle
               Target at FTA

NUMBER OF RETESTS on the level (separate check):
  1 retest   → Require SFP to enter

  2 retests  → Require SFP + MACD divergence
               (over the prior 3 lows/highs)

  3+ retests → PASS ON TRADE (level exhausted)

Special rule:
  If level is close to a fib level → consider placing the limit order
  at the fib level instead of the raw S/R level.
```

`[CONFIRM]`: How do the Touches branch and Retests branch combine? Read of the flowchart is that
both gates must pass (AND logic) — e.g. a 1-touch level needing 2 confluence factors AND (if it
also has retests) satisfying the retest-based SFP/MACD requirement. This needs explicit
confirmation since it materially changes signal frequency.

---

## 4. Entry & Exit Mechanics

- **Entry**: Limit order placed at the level (or at fib level, if level is close to one — rule TBD
  precisely, see 2.9/special rule above)
- **Stop**: Beyond the thrust candle
- **Target**: FTA (First Target Area)
- **Position sizing**: not yet specified — `[TODO]` decide fixed-fractional vs. fixed-risk-per-trade
  before backtest produces meaningful equity curves

---

## 5. Data & Validation Policy

- **Real historical OHLC data only** — no synthetic data generation in this project.
- **No parameter tuning against a single full-history backtest.** All parameter decisions
  (tolerance thresholds, ATR periods, MACD settings) go through walk-forward validation:
  in-sample window for tuning, out-of-sample window for judging — never the same data for both.
- **Statistical significance check required before any result is treated as evidence of edge** —
  trade count, confidence interval on Sharpe, sensitivity to small parameter changes.
- **Journal cross-check**: once the 2022–2023 hardcopy journal is digitized, the coded system's
  historical signals get compared against actual logged trades from that period. Divergence is
  informative either way — reveals either an implementation gap or undocumented discretionary
  judgment in the original trading.

---

## 5a. Falsification Testing (real-data, no synthetic data)

Before trusting any backtest result on the real strategy, the backtest engine itself must be
proven honest — it must not report profit where none should exist. Since this project uses real
data only, falsification is done via **randomization of the real data**, not synthetic price
generation:

- **Random-entry baseline**: run the identical backtest engine (same real OHLC, same costs,
  same exit logic) but replace the decision-tree entry signals with randomized entry timing —
  either uniform random dates at matching frequency to the real signal count, or a
  shuffled/bootstrap resample of the actual signal dates.
- **Expected result**: the random-entry baseline should show a net loss (or at best a
  statistically insignificant result) after realistic spread/slippage costs. Real market
  structure doesn't reward randomly-timed entries — if it does, the backtest engine has a bug
  (lookahead bias, missing costs, incorrect fill logic), independent of whether the *real*
  strategy is any good.
- **Only once the random-entry baseline correctly fails** is the engine trusted enough to
  evaluate the actual decision-tree strategy on the same real data.
- **Edge validation**: the real strategy's result is only meaningful if it clears the
  random-entry baseline by a margin that survives the significance testing in Phase 7 (Sharpe
  confidence interval, deflated Sharpe) — "better than random" needs to be statistically
  distinguishable, not just numerically higher.

This replaces the earlier synthetic-drift falsification approach with a real-data-only
equivalent that serves the same purpose: catching backtest engine bugs before they get
mistaken for a real trading edge.

---

## 6. Implementation Plan

### Phase 0 — Project setup (done)
- `uv` project, Python 3.12
- Core deps: pandas, numpy, scipy, matplotlib, pyarrow
- Dev deps: ruff, jupyter

### Phase 1 — Data pipeline
- `src/data/loader.py` — real OHLC ingestion (broker/data API — TBD which source), Parquet
  local caching, no re-fetch on every run
- `src/data/schema.py` — canonical OHLC DataFrame contract (columns, index, timezone handling)
  every downstream module assumes

### Phase 2 — Level detection primitives
- `src/levels/detection.py` — swing high/low or chosen level-detection method (2.1)
- `src/levels/touches.py` — touch counter (2.3)
- `src/levels/retests.py` — retest counter (2.4)
- Unit tests against hand-labeled real chart examples (pick a handful of known historical
  levels from your journal/memory, assert the counters match what you'd count manually)

### Phase 3 — Confluence factor modules
- `src/confluence/d1_bias.py`
- `src/confluence/fib_levels.py`
- `src/confluence/atr_extension.py`
- Each independently unit-testable against known chart examples

### Phase 4 — Entry confirmation
- `src/confirmation/sfp.py` — SFP detector (2.6)
- `src/confirmation/macd_divergence.py` — divergence over prior 3 lows/highs (2.7)

### Phase 5 — Signal assembly
- `src/signals/decision_tree.py` — wires phases 2–4 into the full decision tree from Section 3
- Pure function(s) on OHLC + detected levels → entry/direction/stop/target columns
- No lookahead: every signal at bar *t* uses only data available at or before *t*'s decision
  point (same discipline as the original Donchian module, carried forward)

### Phase 6 — Backtest engine (extend existing)
- Existing `src/backtest.py` engine (built earlier) gets adapted: limit-order fill logic
  (not market-order-next-open like the Donchian version), stop/target-based exits instead of
  signal-flip exits, realistic spread/slippage per pair
- `src/backtest/fills.py` — limit order fill simulation (did price actually reach the level;
  same-bar fill ambiguity handling)

### Phase 6a — Falsification test (real-data randomization)
- `src/validation/random_baseline.py` — random-entry / shuffled-signal baseline using the
  Phase 6 backtest engine on real data
- Must run and pass (baseline shows no real edge) before Phase 6's engine is trusted for
  evaluating the actual strategy signals from Phase 5

### Phase 7 — Validation framework
- `src/validation/walk_forward.py` — rolling in-sample/out-of-sample split
- `src/validation/significance.py` — Sharpe confidence intervals, deflated Sharpe ratio,
  minimum-sample-size checks
- `src/validation/sensitivity.py` — parameter sensitivity sweep (is the edge robust to small
  threshold changes, or a knife-edge artifact of one specific parameter value)

### Phase 8 — Journal cross-check
- `src/journal/schema.py` — structured schema for digitized journal data (per earlier
  discussion: date, pair, bias, touches, retests, confluence_factors, execution_level, executed,
  exit_type, pnl, macro_thesis, why_note)
- `src/journal/compare.py` — align coded system's historical signals against real logged trades
  by date/pair, report agreement/divergence

### Phase 9 — Reporting
- `src/report/equity_curve.py`, `src/report/metrics_table.py` — plots and tables assembled
  from validation output; this is what actually gets reviewed after each backtest run, not raw
  DataFrames

---

## 7. Production-Grade Setup Notes

- **Config, not hardcoding**: all thresholds (touch tolerance, ATR period, MACD params, SFP wick
  minimum) belong in a config file (`config.yaml` or similar), not literals scattered across
  modules — every parameter here is something walk-forward validation will need to sweep
- **Logging**: structured logging (not print statements) from the data pipeline and backtest
  engine, especially around fills and signal generation, so a bad backtest run can be debugged
  from logs rather than re-run with print statements inserted
- **Testing**: `pytest`, unit tests per module (especially level/touch/retest/SFP detection —
  these are the modules most likely to have off-by-one or lookahead bugs), plus integration
  tests running the full pipeline on a small fixed real-data slice with hand-verified expected
  output
- **Type hints throughout** — this is a numerically sensitive codebase; type errors caught at
  dev time are cheaper than silent NaN propagation in a backtest
- **Version control discipline**: every parameter change that goes into a backtest run should be
  a traceable commit — "which exact code + config produced this equity curve" needs to be
  answerable months later
- **No premature framework adoption** — build raw (as planned in phases above) before reaching
  for vectorbt/backtrader; adopt those later once you understand exactly what a backtest engine
  needs to get right

---

## 8. Immediate Next Steps

1. Resolve `[CONFIRM]` items in Section 2 — these block correct implementation of every module
2. Decide real data source or Phase 1 (broker/API) — needed before any module beyond signal
   logic can be tested against real data
3. Begin Phase 2 (level detection) once 2.1/2.3/2.4 are confirmed