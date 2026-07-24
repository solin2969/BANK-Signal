"""Why does the system lose, and which rules are worth keeping?

Selection is done on the training window only; everything after ``--train-end``
is untouched validation data. Writes ``reports/diagnostics.md``,
``reports/rule_quality.csv`` and the filtered rule file.

    python scripts/diagnostics.py --train-end 2021-12-31
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
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
from banksignal.quality import (
    QualityConfig,
    filter_rule_file,
    rule_quality,
    select_rules,
)


def _md_table(df: pd.DataFrame, floatfmt: str = "{:+.3f}") -> list[str]:
    header = "| " + " | ".join(str(c) for c in df.columns) + " |"
    sep = "| " + " | ".join("---" for _ in df.columns) + " |"
    lines = [header, sep]
    for _, row in df.iterrows():
        cells = [
            floatfmt.format(v) if isinstance(v, (float, np.floating)) else str(v)
            for v in row
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return [*lines, ""]


def _trade_failures(trades: pd.DataFrame, features: pd.DataFrame) -> list[str]:
    """Break the trades down by exit reason, entry rule and market context."""
    if trades.empty:
        return ["No trades.", ""]
    t = trades.copy()
    t["win"] = t["return_pct"] > 0
    t["primary_exit"] = t["exit_reasons"].fillna("").str.split(",").str[0].str.strip()
    ctx = features.reindex(t["entry_time"])
    t["regime"] = ctx["MarketStructure"].to_numpy()
    t["trend"] = np.where(
        ctx["TrendStrength"].to_numpy() > 60, "strong", "weak"
    )
    t["volatility"] = pd.qcut(
        (ctx["ATR"] / ctx["Close"]).to_numpy(), 3, labels=["low", "mid", "high"]
    )

    lines = ["### Losses by exit reason", ""]
    by_exit = (
        t.groupby("primary_exit")
        .agg(
            trades=("return_pct", "size"),
            win_rate=("win", "mean"),
            avg_return=("return_pct", "mean"),
            total_pnl=("pnl", "sum"),
            avg_bars=("bars", "mean"),
            avg_mfe=("mfe", "mean"),
            avg_mae=("mae", "mean"),
        )
        .sort_values("total_pnl")
        .round(3)
        .reset_index()
    )
    lines += _md_table(by_exit, "{:.3f}")

    lines += ["### Result by market context at entry", ""]
    for key in ("regime", "trend", "volatility"):
        grouped = (
            t.groupby(key, observed=True)
            .agg(
                trades=("return_pct", "size"),
                win_rate=("win", "mean"),
                avg_return=("return_pct", "mean"),
                total_pnl=("pnl", "sum"),
            )
            .round(3)
            .reset_index()
        )
        lines += _md_table(grouped, "{:.3f}")

    lines += ["### Entry rules present in losing trades", ""]
    rows = []
    for name, group in _explode_reasons(t, "entry_reasons").groupby("reason"):
        if len(group) < 30:
            continue
        rows.append(
            {
                "rule": name,
                "trades": len(group),
                "win_rate": group["win"].mean(),
                "avg_return": group["return_pct"].mean(),
                "total_pnl": group["pnl"].sum(),
            }
        )
    worst = pd.DataFrame(rows).sort_values("avg_return").round(3)
    lines += _md_table(worst.head(20), "{:.3f}")

    lines += [
        "### Cost of churn",
        "",
        f"* trades: {len(t)}, average holding time: {t['bars'].mean():.1f} bars",
        f"* fees+slippage paid: {t['fees'].sum():.0f} on {t['pnl'].sum() + t['fees'].sum():.0f} gross PnL"
        if "fees" in t
        else "",
        f"* average MFE {t['mfe'].mean():+.2f}% vs average MAE {t['mae'].mean():+.2f}%"
        f" - {100 * (t['mfe'] > 1.0).mean():.0f}% of trades were more than 1% in profit at some point",
        "",
    ]
    return lines


def _explode_reasons(trades: pd.DataFrame, column: str) -> pd.DataFrame:
    t = trades.copy()
    t["reason"] = t[column].fillna("").str.split(",")
    t = t.explode("reason")
    t["reason"] = t["reason"].str.strip()
    return t[t["reason"] != ""]


def main() -> int:  # noqa: C901
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", nargs="+", default=sorted(str(p) for p in Path("data").glob("*.parquet")))
    ap.add_argument("--rules", default="rules/bank.csv")
    ap.add_argument("--train-end", default="2021-12-31")
    ap.add_argument("--filtered", default="rules/bank_filtered.csv")
    ap.add_argument("--out", default="reports/diagnostics.md")
    ap.add_argument("--quality-csv", default="reports/rule_quality.csv")
    args = ap.parse_args()

    candles = load_candles(args.data)
    train = slice_period(candles, end=args.train_end)
    features = build_features(train)
    rule_text = Path(args.rules).read_text(encoding="utf-8")
    engine = SignalEngine(load_rules(args.rules))
    output = engine.evaluate(features)

    cfg = QualityConfig()
    quality = rule_quality(engine, output.fired, train["Close"], cfg)
    keep, report = select_rules(quality)
    Path(args.quality_csv).parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(args.quality_csv, index=False)

    filtered_text = filter_rule_file(rule_text, keep)
    Path(args.filtered).write_text(filtered_text, encoding="utf-8")

    result = Backtester(engine, BacktestConfig(allow_short=False, entry_threshold=50.0, min_hold_bars=12, stop_atr_mult=2.5)).run(features, output)
    metrics = compute_metrics(result.equity, result.trades, train["Close"])

    lines = [
        "# Diagnostics",
        "",
        f"Training window `{train.index[0]}` -> `{train.index[-1]}` ({len(train)} bars). "
        "Every number below is measured on this window only; the filtered rule file it "
        "produces is validated on later data.",
        "",
        "## 1. Why the trades fail",
        "",
        f"Baseline: {metrics.trades} trades, win rate {metrics.win_rate_pct:.1f}%, "
        f"expectancy {metrics.expectancy_pct:+.3f}% per trade, profit factor "
        f"{metrics.profit_factor:.2f}.",
        "",
    ]
    lines += _trade_failures(result.trades, features)

    lines += [
        "## 2. Rule quality",
        "",
        f"Kept **{len(keep)}** of {len(quality)} directional rules "
        f"(min {cfg.min_signals} signals, max {cfg.max_frequency:.0%} firing rate, "
        f"edge >= {cfg.min_edge}pp with t >= {cfg.min_tstat} on at least "
        f"{cfg.min_positive_horizons} of the horizons {cfg.horizons}).",
        "",
        "### Rejection reasons",
        "",
    ]
    reasons = report["reason"].value_counts().rename_axis("reason").reset_index(name="rules")
    lines += _md_table(reasons, "{:.0f}")

    cols = ["rule", "action", "signals", "frequency", *[f"edge_{h}h" for h in cfg.horizons], *[f"t_{h}h" for h in cfg.horizons], "reason"]
    lines += ["### Kept rules", ""]
    lines += _md_table(report[report["keep"]][cols].round(3), "{:.3f}")
    lines += ["### Worst 15 rejected rules", ""]
    lines += _md_table(report.sort_values("edge_mean").head(15)[cols].round(3), "{:.3f}")

    test = slice_period(candles, start=args.train_end)
    if len(test) > max(cfg.horizons) * 10:
        test_output = engine.evaluate(build_features(test))
        test_quality = rule_quality(engine, test_output.fired, test["Close"], cfg)
        merged = report.set_index("rule").join(
            test_quality.set_index("rule")[
                [*[f"edge_{h}h" for h in cfg.horizons], "signals"]
            ],
            rsuffix="_oos",
        )
        kept = merged[merged["keep"]]
        mid = cfg.horizons[len(cfg.horizons) // 2]
        persisted = int((kept[f"edge_{mid}h_oos"] > 0).sum())
        lines += [
            "## 3. Does the selected edge persist?",
            "",
            f"Out-of-sample window `{test.index[0]}` -> `{test.index[-1]}`. "
            f"**{persisted} of {len(kept)}** kept rules still have a positive "
            f"{mid}h edge there.",
            "",
        ]
        cols_oos = [
            "action",
            "signals",
            *[f"edge_{h}h" for h in cfg.horizons],
            "signals_oos",
            *[f"edge_{h}h_oos" for h in cfg.horizons],
        ]
        lines += _md_table(kept[cols_oos].round(3).reset_index(), "{:.3f}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwritten: {out}, {args.quality_csv}, {args.filtered}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
