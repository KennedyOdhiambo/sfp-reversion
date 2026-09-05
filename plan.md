# FX Level/SFP Mean-Reversion Strategy

## Status: v0.2 — definitions resolved (see §2). Ready for phased implementation, step by step.

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

Each item below is a **precise, coded definition** (resolved in the v0.2 refinement pass).
Values marked `(tunable)` are starting points that walk-forward validation (§5/Phase 7) may
adjust — the *logic* is fixed, only the numbers are subject to tuning.

### 2.1 Level — RESOLVED: fractal swing high/low
A significant support/resistance price point, detected as a **fractal swing high/low**: bar
`t` is a swing high iff its high is strictly greater than the highs of the `N = 5` bars on
each side (mirror for lows; `N` is `(tunable)`). Swings smaller than `0.3 × ATR(14)` are
ignored as noise `(tunable)`. Swing prices within `10 ticks` of each other merge into one
level at their mean price `(tunable)`. A level is only *known* from bar `t + N` onward
(swing confirmation lag — no lookahead).

### 2.2 Inverse Level — RESOLVED: defines the target + a hard minimum-R:R filter
The opposing S/R level (e.g. if trading off resistance, the corresponding support). It has two
hard roles, not just context:
1. It **defines the FTA** (see 2.9) — the take-profit target is the nearest opposing level.
2. It is a **hard filter**: skip the trade when the distance to the target is less than
   `1.0 × the stop distance` (minimum 1:1 reward:risk, `(tunable)`).

### 2.3 Touch — RESOLVED: ATR-scaled proximity, forming swing counts
An approach of price to a level: a bar whose high/low comes within `0.1 × ATR(14)` of the
level price `(tunable)`. **The swing that formed the level counts as touch #1.** Touches and
retests are two separate counters: the first approach is the touch; every later approach is a
retest (see 2.4).

### 2.4 Retest — RESOLVED: counting starts with the forming swing as touch #1
A touch occurring *after* the level's establishing touch. Since the forming swing is touch #1,
the next approach is retest #1, then retest #2, and so on. A **break** (close beyond the level
by more than the touch tolerance) deactivates the level — no further signals off it.

### 2.5 Confluence Factors — RESOLVED
Used to gate entries on weaker (fewer-touch) setups. Each factor is a yes/no verdict per bar,
using only data available at that bar:
- **D1 Bias** — bullish when EMA(20) > EMA(50) *and* price made higher highs over the last
  10 bars (mirror for bearish); else neutral. Holds when the bias agrees with the trade
  direction. (All values `(tunable)`.)
- **Fib Level** — the level sits within `0.2 × ATR` of a Fibonacci retracement (ratios 0.382 /
  0.5 / 0.618 / 0.786) drawn over the most recent confirmed swing high→low (or low→high).
- **Level at or past ATR** — the level sits at least `1.0 × ATR(14)` away from the most recent
  confirmed swing (extension = stretched, reactive territory).

### 2.6 SFP (Swing Failure Pattern) — RESOLVED
Price wicks beyond the level, then closes back inside it — a liquidity sweep signaling
exhaustion of the breakout attempt. Long setup: the bar wicks below the level by at least
`0.1 × ATR` **and** closes back above the level by at least `0.05 × ATR` (mirror for shorts).
Both thresholds `(tunable)`.

### 2.7 MACD Divergence (over prior 3 lows/highs) — RESOLVED
Standard parameters 12/26/9, divergence read on the **histogram** (MACD line − signal line).
Bullish: over the prior 3 confirmed swing lows, price makes a lower low while the histogram
makes a higher low (mirror for bearish). Only swings confirmed at least `swing_lookback` bars
before the current bar may be used (no lookahead).

### 2.8 Thrust Candle — RESOLVED: the signal bar itself
The candle that triggers stop placement is the **signal bar** (the bar on which all gates
pass — typically the bar that printed the SFP wick). The stop goes beyond that bar's extreme
(high for shorts, low for longs) plus a `0.1 × ATR` buffer `(tunable)`. No separate
momentum/engulfing definition.

### 2.9 FTA (First Target Area) — RESOLVED: nearest opposing level
Take-profit target = the **nearest opposing level** from the same §2.1 detection (nearest
resistance above for longs, nearest support below for shorts). Fallback when none exists:
`entry ± 2.0 × ATR`. Combined with the §2.2 minimum-1:1 filter, no trade is taken without a
defined, worthwhile target.

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

**RESOLVED — gate combination: AND logic.** Both gates must pass: a setup needs its
touch-based confluence count AND its retest-based confirmation (SFP / SFP+MACD). A level with
0 retests uses only the touch gate; retests add confirmation on top, never replace the
confluence requirement. Retest counts above 2 exhaust the level (pass). The Inverse Level is
not a third gate — its role is target + minimum-R:R filter per §2.2.

---

## 4. Entry & Exit Mechanics

- **Entry**: Limit order placed at the level (or at fib level, if level is close to one — rule TBD
  precisely, see 2.9/special rule above)
- **Stop**: Beyond the thrust candle
- **Target**: FTA (First Target Area)
- **Position sizing**: fixed-fractional, risking **1.0% of equity per trade** `(tunable)`.
  Units = risk amount ÷ stop distance. One open position at a time.

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

## 6. Implementation Plan (v0.2)

House rules for every phase:
- **One phase at a time.** A phase is finished only when its Definition of Done holds.
- **Tests per phase.** `pytest` must be green before the next phase starts.
- **Config, not hardcoding.** Every `(tunable)` number lives in `config.yaml`.
- **No lookahead.** Any output at bar `t` may use only data available at or before `t`.
- **ATR regime through the prior bar.** Every ATR-scaled threshold at bar `t` uses ATR up to
  `t−1` — a violent bar must never set its own hurdle.
- **One commit per phase.** "Which code + config produced this result" must stay answerable.
- Unit tests may use tiny hand-made OHLC frames; anything resembling a backtest result must
  use real data (§5).

### Phase 0 — Project setup
- `uv` project, Python 3.12; core deps pandas/numpy/scipy/matplotlib/pyarrow/pyyaml; dev deps
  pytest/ruff.
- `config.yaml` holding every `(tunable)` number from §2; empty `src/sfp_reversion` package.
- Done when: `uv sync` succeeds, `pytest` collects (0 tests), config loads.

### Phase 1 — OHLC schema (the contract)
- `src/sfp_reversion/data/schema.py` — canonical frame: UTC DatetimeIndex named `timestamp`,
  float columns `open/high/low/close/volume`; validate/normalize, concat, empty helpers.
- Done when: unit tests pass — good frames accepted; bad frames (naive timezone, duplicate
  timestamps, high<low, missing columns) rejected.

### Phase 2 — Data loader (Yahoo + cache)
- `src/sfp_reversion/data/loader.py` — pull real OHLC from Yahoo Finance chart API (keyless,
  global; OANDA onboarding excludes Kenya, Stooq is bot-walled). One bulk request per pair
  (daily history to ~2003), merged into a local parquet cache
  (`data/cache/{pair}_{granularity}.parquet`). Never re-fetch cached ranges; network failure
  degrades to cache with a warning (hard error only when the cache is empty too). No creds.
- Done when: a live fetch for one pair loads, validates, caches, and reloads from cache;
  unit tests with a stub fetcher cover merging, slicing, and corrupt-cache recovery.

### Phase 3 — Swing + level detection (§2.1)
- `src/sfp_reversion/levels/detection.py` — fractal swings (N=5 bars each side, min 0.3×ATR
  magnitude) clustered within 10 ticks into levels at their mean price; a level is only known
  from its confirmation bar onward.
- Levels are detected on the **daily** frame (Option A: daily = where the levels are,
  hourly = when entries trigger). Entry-timeframe consumption is Phase 10's job.
- Done when: detected levels match hand-counted levels on 2–3 hand-labeled real-chart excerpts.

### Phase 4 — Touch / retest counters (§2.3, §2.4)
- Touch = bar within 0.1×ATR of the level; the forming swing is touch #1; later approaches
  are retests; a close beyond tolerance = break (level dead).
- In `src/sfp_reversion/levels/` alongside detection. The module is timeframe-agnostic: it
  counts approaches on whatever frame it is given — under Option A that will be hourly bars
  against daily-detected levels (wired in Phase 10).
- Done when: counters match hand counts on labeled excerpts, including one break case and one
  3-retest exhaustion case.

### Phase 5 — D1 bias (§2.5)
- `src/sfp_reversion/confluence/d1_bias.py` — EMA20/50 + 10-bar confirmation; output in
  {−1, 0, +1}; matcher for trade direction.
- Done when: unit tests on trending, ranging, and trend-flip cases.

### Phase 6 — Fib levels (§2.5 + special limit rule)
- `src/sfp_reversion/confluence/fib_levels.py` — retracements of the most recent confirmed
  swing (0.382/0.5/0.618/0.786), proximity 0.2×ATR, fib-override price for limit placement.
- Done when: levels match hand-computed fibs on a known swing; override triggers only within
  proximity.

### Phase 7 — ATR extension (§2.5)
- `src/sfp_reversion/confluence/atr_extension.py` — level ≥ 1.0×ATR(14) from the recent-swing
  reference.
- Done when: true/false cases verified on hand-picked bars.

### Phase 8 — SFP detector (§2.6)
- `src/sfp_reversion/confirmation/sfp.py` — wick ≥ 0.1×ATR beyond the level, close ≥ 0.05×ATR
  back inside, per direction.
- Done when: textbook SFP bars detected; near-misses (wick too short, close barely inside)
  rejected.

### Phase 9 — MACD divergence (§2.7)
- `src/sfp_reversion/confirmation/macd_divergence.py` — 12/26/9 histogram divergence over the
  prior 3 confirmed swings, no lookahead.
- Done when: a known historical divergence flags true; a non-divergent lower-low stays false.

### Phase 10 — Decision-tree assembly (§3)
- `src/sfp_reversion/signals/decision_tree.py` — Phases 3–9 wired with AND gates, the §2.2
  minimum-1:1 R:R filter, FTA targets, and fib-override limits. Two inputs: the **hourly**
  (entry-timeframe) frame and the **daily** frame (D1 bias context). Pure function:
  (hourly, daily) → signal table (timestamp, direction, limit, stop, target, touches, retests,
  factors…).
- Done when: integration test on a small fixed real-data slice produces hand-verified rows,
  including a lookahead probe (no signal may reference future bars).

### Phase 11 — Backtest engine
- `src/sfp_reversion/backtest/` — limit-order fills from bar t+1, stop-first exit priority,
  spread+slippage costs, 1%-risk sizing, one position at a time, per-trade table + equity curve.
- Done when: a hand-worked 2-trade scenario reproduces exact fills and PnL, with costs visibly
  applied.

### Phase 12 — Falsification gate (§5a)
- `src/sfp_reversion/validation/random_baseline.py` — random-entry baseline on the same engine
  and data must show no edge. If it shows profit, the engine has a bug: fix it before Phase 13.
- Done when: baseline prints loss/insignificance and an explicit PASS/FAIL verdict.

### Phase 13 — Validation framework
- `src/sfp_reversion/validation/` — walk-forward (in-sample tune / out-of-sample judge),
  Sharpe confidence + deflated Sharpe, parameter sensitivity sweep.
- Done when: runs end-to-end on real data and reports "robust vs knife-edge" per parameter.

### Phase 14 — Reporting
- `src/sfp_reversion/report/` — equity-curve plot + metrics table built from validation output.
- Done when: one command produces the plot + table a human actually reviews.

### Phase 15 — Journal cross-check (deferred)
- Needs your digitized 2022–23 journal as input. `src/sfp_reversion/journal/` — schema + compare
  report aligning coded signals against logged trades by date/pair.
- Done when: agreement/divergence report runs on real journal rows.

### Phase 16 — CLI wiring
- `fetch / signals / backtest / validate / journal` commands tying all phases together.
- Done when: each command runs end-to-end from a clean cache.

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

1. ~~Resolve `[CONFIRM]` items in Section 2~~ — done in v0.2 (all §2 items resolved;
   numbers marked `(tunable)` go through walk-forward, never hand-tuned on full history)
2. ~~Data source~~ — Yahoo Finance (keyless, works from Kenya) decided in Phase 2; no creds.
3. Work the phases in order starting at Phase 0 — each phase's Definition of Done holds
   before the next begins. Reference (not copy-paste) implementation lives on branch
   `archive/full-implementation-20260905`; we rebuild for understanding.