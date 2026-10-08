# Philosophy — Trader Dante, as we understand him

> Background and principles. Not a spec. The tradable spec lives in `strategy.md` (Setup A / SFP only). Everything in code is trial/experimentation until walk-forward + significance say otherwise. Education only, not financial advice.

## 1. Who he is (public record)
- Tom Dante (@Trader_Dante), London. Trading since 1999. ~7 years struggling, then profitable, then a stint at a London prop futures firm, then independent.
- Still posting 2007 → 2026. Blunt style. No audited public track record found — critics flag this, supporters point to longevity + prop background. Treat all performance claims (including a NexusFi user's "~55% / 1.7R over 18 months") as unverified anecdotes.

## 2. What he trades (two setups — we only build one for now)
- **Setup A — Swing Failure Pattern (SFP).** Price stabs beyond a key swing with the wick, closes back inside. Fade the failed break. H1 trigger, Daily context. This is the signature and the only thing we systematize right now.
- **Setup B — Breakout-then-return, touch-graded.** Fresh break, first return, graded 3 touches = take / 2 touches = 1 confirmation / 1 touch = 2 confirmations (confirmations: daily pin/engulfing/SFP, fib 38/50/61, ATR stretch). Parked. Not in `strategy.md`, not in the build.
- **Short-term Bund method (Module 3).** Intraday prop method. Agenda titles only are public. Out of scope.

## 3. Core beliefs behind both setups
1. **Obviousness is liquidity.** Trade levels everyone sees (prior swings, equal highs/lows, day/session extremes). If you squint, there is no fuel.
2. **The close decides.** Wick beyond = sweep (stops + breakout chasers filled). Close back inside = they are trapped — that is the signal. Close beyond = genuine break — do not fade.
3. **Fresh beats exhausted.** Levels touched many times are weak. Dante's Setup B grades this explicitly; Setup A inherits it: clean first failures > chewed-up shelves.
4. **Higher timeframe chooses location, lower timeframe delivers trigger.** Daily structure for levels/targets, H1 for the SFP candle, 5m optional for entry refinement.
5. **Geometry first, prediction never.** Entry on the rejection close, stop beyond the sweep extreme + ATR, target the next opposing pool. Skip when the math doesn't pay.
6. **Process is half the edge.** Daily plan sheet, pre-marked areas, stupid-trade scoring (Demon Finder), weekly review. No setup survives without this.

## 4. What is public vs what we invent
- Public: concepts above, ATR-buffered stops, fib ratios 38/50/61, 20-period ATR mention, "very long original wick" skip, warning-sign exit (first H1 close back through the extreme), 5m refinement tip.
- NOT public: exact swing lookback, touch tolerance, wick/close ATR fractions, fib proximity, stop-buffer ATR multiple, min R:R. Every number in `config.yaml` is our operational choice, tunable via walk-forward — never presented as "Dante's numbers".
- This repo's old additions (MACD divergence, confluence AND-gates, touch/retest counters fused into one tree) are **not Dante** — they were our trial scaffold. The new plan strips them out of Setup A's path.

## 5. How to use these docs
- `philosophy.md` (this file) — why we trade this way. Changes rarely.
- `strategy.md` — exact Setup A rules, flowchart, parameters.
- Code is guilty until proven innocent: random-baseline gate, walk-forward OOS, Sharpe CI + deflated Sharpe, sensitivity hills-not-spikes.
- `tmp/` — raw research notes and links. Scratch, not truth.

## Sources
Per-source links: `tmp/sources.md`. Curriculum titles: `tmp/official-curriculum.md`. Paraphrased 2-page rules: `tmp/dante-strategy-public-summary.md`. Forum color: `tmp/community-notes.md`.
