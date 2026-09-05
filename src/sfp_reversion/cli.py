"""CLI: fetch / signals / backtest / validate. End-to-end entry point."""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from sfp_reversion.backtest.engine import BacktestParams, run_backtest
from sfp_reversion.config import get_config, setup_logging
from sfp_reversion.data.loader import load_ohlc
from sfp_reversion.report import metrics_table, plot_equity_curve
from sfp_reversion.signals import DecisionTreeParams, generate_signals
from sfp_reversion.validation import (
    baseline_passes,
    run_random_baseline,
    sweep_parameter,
    walk_forward_evaluate,
)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sfp-reversion", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    f = sub.add_parser("fetch", help="Pull OHLC into the local cache")
    f.add_argument("pair")
    f.add_argument("--granularity", default=None)
    f.add_argument("--start", default=None, help="YYYY-MM-DD")
    f.add_argument("--end", default=None, help="YYYY-MM-DD")

    s = sub.add_parser("signals", help="Generate decision-tree signals")
    s.add_argument("pair")
    s.add_argument("--out", default=None, help="CSV output path")

    b = sub.add_parser("backtest", help="Backtest + random-baseline gate")
    b.add_argument("pair")
    b.add_argument("--n-baseline", type=int, default=20)
    b.add_argument("--seed", type=int, default=0)
    b.add_argument("--out-dir", default=None)

    v = sub.add_parser("validate", help="Walk-forward + optional parameter sweep")
    v.add_argument("pair")
    v.add_argument("--parameter", default=None)
    v.add_argument("--values", nargs="+", type=float, default=None)
    v.add_argument("--is-years", type=float, default=None)
    v.add_argument("--oos-years", type=float, default=None)
    return p


def _dt(value: str | None) -> datetime | None:
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC) if value else None


def _frames(pair: str, granularity: str, start: str | None, end: str | None) -> tuple:
    hourly = load_ohlc(pair, _dt(start), _dt(end), granularity=granularity or "H1")
    daily = load_ohlc(pair, _dt(start), _dt(end))
    return hourly, daily


def _cmd_fetch(args: argparse.Namespace) -> int:
    df = load_ohlc(args.pair, _dt(args.start), _dt(args.end), granularity=args.granularity)
    print(f"{args.pair}: {len(df)} bars ({df.index.min()} -> {df.index.max()})")
    return 0


def _cmd_signals(args: argparse.Namespace) -> int:
    hourly, daily = _frames(args.pair, "H1", None, None)
    sig = generate_signals(hourly, daily)
    print(f"{len(sig)} signals")
    if not sig.empty:
        print(sig.to_string())
        if args.out:
            sig.to_csv(args.out, index=False)
            print(f"wrote {args.out}")
    return 0


def _cmd_backtest(args: argparse.Namespace) -> int:
    cfg = get_config()
    hourly, daily = _frames(args.pair, "H1", None, None)
    params = BacktestParams.from_config()
    sig = generate_signals(hourly, daily)
    res = run_backtest(hourly, sig, params)
    print(metrics_table(res.trades_df, res.equity_curve, params.min_equity).to_string(index=False))
    out_dir = Path(args.out_dir or cfg.get("report.output_dir", "reports"))
    curve = plot_equity_curve(res.equity_curve, out_dir / f"{args.pair}_equity.png")
    print(f"equity curve: {curve}")
    pnls = run_random_baseline(hourly, max(len(sig), 1), params, args.n_baseline, args.seed)
    passed, s = baseline_passes(pnls)
    print(f"random baseline: mean={s['mean']:.2f} p={s['p']:.3f} -> {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 2


def _cmd_validate(args: argparse.Namespace) -> int:
    cfg = get_config()
    wf = cfg.section("validation").get("walk_forward", {})
    hourly, daily = _frames(args.pair, "H1", None, None)
    params, bt = DecisionTreeParams.from_config(), BacktestParams.from_config()

    if args.parameter:
        values = args.values or [0.05, 0.1, 0.15, 0.2]

        def run(v: float) -> float:
            sig = generate_signals(hourly, daily, replace(params, **{args.parameter: v}))
            res = run_backtest(hourly, sig, bt)
            return float(res.trades_df["pnl"].sum()) if not res.trades_df.empty else 0.0

        r = sweep_parameter(list(values), run)
        for v, s in zip(r.values, r.scores, strict=True):
            print(f"  {args.parameter}={v}: pnl={s:.2f}")
        print(f"best={r.best_value} robust={'yes' if r.robust else 'NO'}")
        return 0

    def score_fn(is_h, is_d, oos_h, oos_d) -> tuple[float, int]:
        import pandas as pd

        h = pd.concat([is_h, oos_h])
        d = pd.concat([is_d, oos_d]) if not is_d.empty else oos_d
        sig = generate_signals(h, d, params)
        sig = sig[sig["timestamp"] >= oos_h.index[0]]
        res = run_backtest(h, sig, bt)
        n = len(res.trades_df)
        return (float(res.trades_df["pnl"].sum()) if n else 0.0, n)

    res = walk_forward_evaluate(
        hourly,
        daily,
        score_fn,
        args.is_years or float(wf.get("in_sample_years", 0.75)),
        args.oos_years or float(wf.get("out_of_sample_years", 0.25)),
    )
    if not res:
        print("no walk-forward windows in range")
        return 0
    for w in res:
        print(f"{w.oos_start.date()} -> {w.oos_end.date()}: pnl={w.score:.2f} trades={w.n_trades}")
    return 0


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    args = _parser().parse_args(argv)
    handlers = {
        "fetch": _cmd_fetch,
        "signals": _cmd_signals,
        "backtest": _cmd_backtest,
        "validate": _cmd_validate,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
