"""Run the compression-breakout strategy and write its report + equity curve.

    python scripts/breakout_backtest.py --train-end 2024-01-01 --out reports/breakout
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from banksignal import load_candles
from banksignal.breakout import BreakoutConfig, run_breakout, summarise


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", nargs="+", default=sorted(str(p) for p in Path("data").glob("*.parquet")))
    ap.add_argument("--train-end", default="2024-01-01")
    ap.add_argument("--out", default="reports/breakout")
    ap.add_argument("--no-short", action="store_true")
    ap.add_argument("--optimistic", action="store_true", help="disable causal trailing stop")
    args = ap.parse_args()

    candles = load_candles(args.data)
    if candles.index.tz is None:
        candles.index = candles.index.tz_localize("utc")
    cfg = BreakoutConfig(allow_short=not args.no_short, causal_trailing=not args.optimistic)
    trades = run_breakout(candles, cfg)
    report = summarise(trades, args.train_end)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    report.trades.to_csv(out / "trades.csv", index=False)
    (out / "metrics.json").write_text(json.dumps(report.metrics, indent=2), encoding="utf-8")
    _plot(report, candles["Close"], out / "equity_curve.png")

    print(json.dumps(report.metrics, indent=2))
    print(f"\nwritten: {out}/trades.csv, metrics.json, equity_curve.png")
    return 0


def _plot(report, price, path: Path) -> None:
    t = report.trades
    eq = t.set_index("entry_time")["equity"]
    fig, (ax, ax2) = plt.subplots(
        2, 1, figsize=(13, 8), gridspec_kw={"height_ratios": [3, 1]}, sharex=True
    )
    ax.plot(eq.index, eq.values, color="#1f77b4", lw=1.2, label="strategy equity (x)")
    bh = price / price.iloc[0]
    ax.plot(bh.index, bh.values, color="#999", lw=1.0, alpha=0.7, label="buy & hold (x)")
    ax.axvline(report.train_end, color="red", ls=":", lw=1.5, label="train/test split")
    ax.axhline(1.0, color="k", ls="--", lw=0.6)
    ax.set_yscale("log")
    ax.set_ylabel("equity multiple (log)")
    ax.set_title("BTCUSDT compression-breakout — causal staircase exit")
    ax.legend(loc="upper left")
    dd = eq / eq.cummax() - 1
    ax2.fill_between(dd.index, dd.values * 100, 0, color="#d62728", alpha=0.4)
    ax2.set_ylabel("drawdown %")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
