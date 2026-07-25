"""Command line interface: backtest the bank.csv system or emit live signals."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .backtest import BacktestConfig, Backtester
from .data import load_candles, slice_period
from .engine import EngineConfig, SignalEngine
from .features import FeatureConfig, build_features
from .metrics import compute_metrics
from .report import write_report
from .rules import load_rules

DEFAULT_RULES = "rules/bank.csv"
DEFAULT_DATA = "data/*.parquet"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="banksignal")
    sub = parser.add_subparsers(dest="command", required=True)

    bt = sub.add_parser("backtest", help="run a backtest over historical candles")
    _common(bt)
    bt.add_argument("--out", default="reports", help="report output directory")
    bt.add_argument("--equity", type=float, default=10_000.0)
    bt.add_argument("--size", type=float, default=0.25, help="base position size")
    bt.add_argument("--entry-threshold", type=float, default=50.0)
    bt.add_argument("--exit-threshold", type=float, default=0.0)
    bt.add_argument("--min-hold", type=int, default=12)
    bt.add_argument("--stop-atr", type=float, default=2.5)
    bt.add_argument("--trail-atr", type=float, default=0.0)
    bt.add_argument("--fee", type=float, default=0.0004)
    bt.add_argument("--no-short", action="store_true")

    sig = sub.add_parser("signals", help="print the signals of the most recent bars")
    _common(sig)
    sig.add_argument("--tail", type=int, default=10)

    show = sub.add_parser("rules", help="summarise the parsed rule file")
    show.add_argument("--rules", default=DEFAULT_RULES)

    args = parser.parse_args(argv)
    if args.command == "rules":
        return _cmd_rules(args)
    if args.command == "signals":
        return _cmd_signals(args)
    return _cmd_backtest(args)


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--data", nargs="+", default=None, help="candle parquet/csv files")
    p.add_argument("--rules", default=DEFAULT_RULES)
    p.add_argument("--start", default=None)
    p.add_argument("--end", default=None)


def _resolve_data(paths: list[str] | None) -> list[str]:
    if paths:
        return paths
    found = sorted(str(p) for p in Path().glob(DEFAULT_DATA))
    if not found:
        raise SystemExit(f"no candle files found, pass --data (looked for {DEFAULT_DATA})")
    return found


def _prepare(args: argparse.Namespace):
    candles = slice_period(load_candles(_resolve_data(args.data)), args.start, args.end)
    features = build_features(candles, FeatureConfig())
    engine = SignalEngine(load_rules(args.rules), EngineConfig())
    return candles, features, engine, engine.evaluate(features)


def _cmd_rules(args: argparse.Namespace) -> int:
    rules = load_rules(args.rules)
    by_phase: dict[str, int] = {}
    by_action: dict[str, int] = {}
    for r in rules:
        by_phase[r.phase] = by_phase.get(r.phase, 0) + 1
        by_action[r.action] = by_action.get(r.action, 0) + 1
    print(json.dumps({"rules": len(rules), "phases": by_phase, "actions": by_action}, indent=2))
    return 0


def _cmd_signals(args: argparse.Namespace) -> int:
    _, features, _, output = _prepare(args)
    cols = ["Direction", "FinalEntryScore", "ExitScore", "BlockScore", "SignalCount"]
    tail = output.frame[cols].tail(args.tail)
    for i in range(len(tail)):
        pos = len(output.frame) - len(tail) + i
        names = ", ".join(output.fired_names(pos)) or "-"
        row = tail.iloc[i]
        print(
            f"{tail.index[i]} | dir={row['Direction']:+.0f} entry={row['FinalEntryScore']:5.1f}"
            f" exit={row['ExitScore']:5.1f} block={row['BlockScore']:5.1f} :: {names}"
        )
    return 0


def _cmd_backtest(args: argparse.Namespace) -> int:
    candles, features, engine, output = _prepare(args)
    cfg = BacktestConfig(
        initial_equity=args.equity,
        base_size=args.size,
        entry_threshold=args.entry_threshold,
        exit_threshold=args.exit_threshold,
        min_hold_bars=args.min_hold,
        stop_atr_mult=args.stop_atr,
        trail_atr_mult=args.trail_atr,
        fee_rate=args.fee,
        allow_short=not args.no_short,
    )
    result = Backtester(engine, cfg).run(features, output)
    metrics = compute_metrics(result.equity, result.trades, candles["Close"])
    paths = write_report(args.out, metrics, result.equity, result.trades, candles["Close"])

    print(json.dumps(metrics.to_dict(), indent=2, default=str))
    print(f"\nreport : {paths['report']}\nchart  : {paths['chart']}\ntrades : {paths['trades']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
