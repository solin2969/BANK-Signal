"""Validate a rule file out-of-sample with the parameters chosen in-sample.

Also reports the out-of-sample result of the whole in-sample top list, which
shows whether the choice was luck or the parameters are simply flat:

    python scripts/validate.py --rules rules/bank_filtered.csv \
        --grid reports/optimization_filtered.csv --train-end 2021-12-31
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from banksignal import (
    BacktestConfig,
    Backtester,
    SignalEngine,
    build_features,
    compute_metrics,
    load_candles,
    load_rules,
    slice_period,
)

PARAMS = [
    "entry_threshold",
    "exit_threshold",
    "min_hold_bars",
    "stop_atr_mult",
    "trail_atr_mult",
    "allow_short",
]


def _md_table(df: pd.DataFrame) -> list[str]:
    lines = [
        "| " + " | ".join(str(c) for c in df.columns) + " |",
        "| " + " | ".join("---" for _ in df.columns) + " |",
    ]
    for _, row in df.iterrows():
        lines.append("| " + " | ".join(str(v) for v in row) + " |")
    return [*lines, ""]


def _run(engine, candles, cfg):
    features = build_features(candles)
    output = engine.evaluate(features)
    result = Backtester(engine, cfg).run(features, output)
    return compute_metrics(result.equity, result.trades, candles["Close"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", nargs="+", default=sorted(str(p) for p in Path("data").glob("*.parquet")))
    ap.add_argument("--rules", default="rules/bank_filtered.csv")
    ap.add_argument("--grid", default="reports/optimization_filtered.csv")
    ap.add_argument("--train-end", default="2021-12-31")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--out", default="reports/validation.md")
    args = ap.parse_args()

    candles = load_candles(args.data)
    train = slice_period(candles, end=args.train_end)
    test = slice_period(candles, start=args.train_end)
    engine = SignalEngine(load_rules(args.rules))

    grid = pd.read_csv(args.grid).sort_values("sharpe", ascending=False)
    rows = []
    for _, row in grid.head(args.top).iterrows():
        cfg = BacktestConfig(
            entry_threshold=float(row["entry_threshold"]),
            exit_threshold=float(row["exit_threshold"]),
            min_hold_bars=int(row["min_hold_bars"]),
            stop_atr_mult=float(row["stop_atr_mult"]),
            trail_atr_mult=float(row["trail_atr_mult"]),
            allow_short=bool(row["allow_short"]),
        )
        m = _run(engine, test, cfg)
        rows.append(
            {
                **{p: row[p] for p in PARAMS},
                "is_return": row["total_return_pct"],
                "is_sharpe": row["sharpe"],
                "oos_return": m.total_return_pct,
                "oos_sharpe": m.sharpe,
                "oos_maxdd": m.max_drawdown_pct,
                "oos_trades": m.trades,
                "oos_profit_factor": m.profit_factor,
            }
        )
    table = pd.DataFrame(rows)

    best = BacktestConfig(
        entry_threshold=float(grid.iloc[0]["entry_threshold"]),
        exit_threshold=float(grid.iloc[0]["exit_threshold"]),
        min_hold_bars=int(grid.iloc[0]["min_hold_bars"]),
        stop_atr_mult=float(grid.iloc[0]["stop_atr_mult"]),
        trail_atr_mult=float(grid.iloc[0]["trail_atr_mult"]),
        allow_short=bool(grid.iloc[0]["allow_short"]),
    )
    windows = {
        "in-sample": train,
        "out-of-sample": test,
        "full period": candles,
    }
    lines = [
        "# Out-of-sample validation",
        "",
        f"rules `{args.rules}`, parameters chosen on data up to `{args.train_end}`:",
        "",
        "```",
        *[f"{p} = {getattr(best, p)}" for p in PARAMS],
        "```",
        "",
        "| window | return % | buy & hold % | max DD % | Sharpe | trades | win % | PF |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for label, window in windows.items():
        m = _run(engine, window, best)
        lines.append(
            f"| {label} | {m.total_return_pct:+.1f} | {m.buy_hold_return_pct:+.1f} |"
            f" {m.max_drawdown_pct:.1f} | {m.sharpe:.2f} | {m.trades} |"
            f" {m.win_rate_pct:.1f} | {m.profit_factor:.2f} |"
        )
    lines += [
        "",
        f"## Out-of-sample result of the {args.top} best in-sample parameter sets",
        "",
        f"median OOS return **{table['oos_return'].median():+.1f}%**, "
        f"{(table['oos_return'] > 0).mean():.0%} of them positive.",
        "",
        *_md_table(table.round(2)),
    ]
    Path(args.out).write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
