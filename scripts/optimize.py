"""Grid search of the execution parameters on an in-sample window.

The rule file itself is never tuned - only how the backtester acts on its
signals (entry/exit thresholds, holding time, stops). Run:

    python scripts/optimize.py --train-end 2021-12-31 --top 15
"""

from __future__ import annotations

import argparse
import itertools
import json
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

GRID = {
    "entry_threshold": [50.0, 60.0, 70.0, 80.0],
    "exit_threshold": [0.0, 60.0, 80.0, 95.0],
    "min_hold_bars": [1, 4, 12],
    "stop_atr_mult": [1.5, 2.5, 4.0],
    "trail_atr_mult": [0.0, 3.0],
    "allow_short": [True, False],
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", nargs="+", default=sorted(str(p) for p in Path("data").glob("*.parquet")))
    ap.add_argument("--rules", default="rules/bank.csv")
    ap.add_argument("--train-end", default="2021-12-31")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--out", default="reports/optimization.csv")
    args = ap.parse_args()

    candles = load_candles(args.data)
    train = slice_period(candles, end=args.train_end)
    features = build_features(train)
    engine = SignalEngine(load_rules(args.rules))
    output = engine.evaluate(features)

    keys = list(GRID)
    rows = []
    for combo in itertools.product(*(GRID[k] for k in keys)):
        params = dict(zip(keys, combo, strict=True))
        cfg = BacktestConfig(**params)
        result = Backtester(engine, cfg).run(features, output)
        m = compute_metrics(result.equity, result.trades, train["Close"])
        rows.append({**params, **m.to_dict()})
        print(
            f"{params} -> return {m.total_return_pct:8.2f}%  dd {m.max_drawdown_pct:7.2f}%"
            f"  sharpe {m.sharpe:5.2f}  trades {m.trades}",
            flush=True,
        )

    df = pd.DataFrame(rows).sort_values("sharpe", ascending=False)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)
    print("\nTOP RESULTS")
    cols = [*keys, "total_return_pct", "max_drawdown_pct", "sharpe", "profit_factor", "trades"]
    print(df[cols].head(args.top).to_string(index=False))
    best = df.iloc[0]
    print("\nbest:", json.dumps({k: best[k] for k in keys}, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
