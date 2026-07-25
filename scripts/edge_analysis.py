"""Measure whether the signals carry directional information at all.

Independently of the backtester, this compares the forward return after each
signal with the unconditional forward return of the same window. A rule only
has an edge if ``mean_fwd - baseline`` is positive for LONG rules (negative for
SHORT rules) by more than trading costs.

    python scripts/edge_analysis.py --horizons 6 24 72 --out reports/edge_analysis.md
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from banksignal import (
    SignalEngine,
    build_features,
    load_candles,
    load_rules,
    slice_period,
)
from banksignal.engine import LONG_ACTIONS, SHORT_ACTIONS


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", nargs="+", default=sorted(str(p) for p in Path("data").glob("*.parquet")))
    ap.add_argument("--rules", default="rules/bank.csv")
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--horizons", nargs="+", type=int, default=[6, 24, 72])
    ap.add_argument("--min-signals", type=int, default=50)
    ap.add_argument("--out", default="reports/edge_analysis.md")
    args = ap.parse_args()

    candles = slice_period(load_candles(args.data), args.start, args.end)
    features = build_features(candles)
    engine = SignalEngine(load_rules(args.rules))
    output = engine.evaluate(features)
    close = candles["Close"]

    lines = ["# Signal edge analysis", "", f"period `{close.index[0]}` -> `{close.index[-1]}`", ""]
    for hz in args.horizons:
        fwd = (close.shift(-hz) / close - 1.0) * 100.0
        baseline = float(fwd.mean())
        lines += [
            f"## Forward return over {hz}h (baseline {baseline:+.3f}%)",
            "",
            "| bucket | signals | mean fwd % | edge vs baseline |",
            "| --- | ---: | ---: | ---: |",
        ]
        frame = pd.DataFrame(
            {
                "dir": output.frame["Direction"],
                "score": output.frame["FinalEntryScore"],
                "fwd": fwd,
            }
        ).dropna()
        buckets = pd.cut(frame["score"], [0, 40, 60, 80, 101])
        grouped = frame.groupby([frame["dir"], buckets], observed=True)["fwd"].agg(
            ["mean", "count"]
        )
        for (direction, bucket), row in grouped.iterrows():
            label = {1.0: "LONG", -1.0: "SHORT", 0.0: "FLAT"}[direction]
            edge = row["mean"] - baseline
            if direction < 0:
                edge = -edge
            lines.append(
                f"| {label} score {bucket} | {int(row['count'])} | {row['mean']:+.3f} | {edge:+.3f} |"
            )
        lines.append("")

        rows = []
        for rule in engine.rules:
            if rule.action not in LONG_ACTIONS | SHORT_ACTIONS:
                continue
            mask = output.fired[rule.name].reindex(fwd.index).fillna(False)
            hits = fwd[mask.to_numpy()].dropna()
            if len(hits) < args.min_signals:
                continue
            sign = 1.0 if rule.action in LONG_ACTIONS else -1.0
            rows.append(
                {
                    "rule": rule.name,
                    "action": rule.action,
                    "signals": len(hits),
                    "mean_fwd": float(hits.mean()),
                    "edge": sign * (float(hits.mean()) - baseline),
                }
            )
        table = pd.DataFrame(rows).sort_values("edge", ascending=False)
        lines += [
            f"### Directional rules ranked by {hz}h edge",
            "",
            "| rule | action | signals | mean fwd % | edge |",
            "| --- | --- | ---: | ---: | ---: |",
        ]
        for _, r in table.iterrows():
            lines.append(
                f"| {r['rule']} | {r['action']} | {int(r['signals'])} |"
                f" {r['mean_fwd']:+.3f} | {r['edge']:+.3f} |"
            )
        lines.append("")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:40]))
    print(f"\nwritten: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
