"""Markdown + chart reporting for backtest runs."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from .metrics import Metrics, signal_stats, yearly_returns  # noqa: E402


def write_report(
    out_dir: str | Path,
    metrics: Metrics,
    equity: pd.Series,
    trades: pd.DataFrame,
    price: pd.Series,
) -> dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    chart = out / "equity_curve.png"
    _plot(equity, price, chart)

    trades_csv = out / "trades.csv"
    trades.to_csv(trades_csv, index=False)

    summary = out / "backtest_report.md"
    summary.write_text(_markdown(metrics, equity, trades), encoding="utf-8")
    return {"report": summary, "chart": chart, "trades": trades_csv}


def _plot(equity: pd.Series, price: pd.Series, path: Path) -> None:
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(12, 8), sharex=True, gridspec_kw={"height_ratios": [3, 1]}
    )
    buy_hold = equity.iloc[0] * price / price.iloc[0]
    ax1.plot(equity.index, equity.to_numpy(), label="bank.csv system", color="#1f77b4")
    ax1.plot(
        buy_hold.index,
        buy_hold.to_numpy(),
        label="buy & hold BTC",
        color="#999999",
        linestyle="--",
    )
    ax1.set_yscale("log")
    ax1.set_ylabel("equity (USDT, log)")
    ax1.legend()
    ax1.grid(alpha=0.3)

    drawdown = 100.0 * (equity / equity.cummax() - 1.0)
    ax2.fill_between(drawdown.index, drawdown.to_numpy(), 0, color="#d62728", alpha=0.5)
    ax2.set_ylabel("drawdown %")
    ax2.grid(alpha=0.3)

    fig.suptitle("BANK-Signal backtest - BTCUSDT 1h")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def _markdown(metrics: Metrics, equity: pd.Series, trades: pd.DataFrame) -> str:
    m = metrics
    lines = [
        "# BANK-Signal backtest report",
        "",
        f"* period: `{m.start}` -> `{m.end}` ({m.bars} 1h bars)",
        f"* equity: `{m.initial_equity:,.0f}` -> `{m.final_equity:,.2f}` USDT",
        "",
        "## Headline",
        "",
        "| metric | value |",
        "| --- | ---: |",
        f"| total return | {m.total_return_pct:,.2f}% |",
        f"| buy & hold | {m.buy_hold_return_pct:,.2f}% |",
        f"| CAGR | {m.cagr_pct:,.2f}% |",
        f"| max drawdown | {m.max_drawdown_pct:,.2f}% |",
        f"| Sharpe | {m.sharpe:,.2f} |",
        f"| Sortino | {m.sortino:,.2f} |",
        f"| Calmar | {m.calmar:,.2f} |",
        f"| trades | {m.trades} ({m.long_trades} long / {m.short_trades} short) |",
        f"| win rate | {m.win_rate_pct:,.2f}% |",
        f"| profit factor | {m.profit_factor:,.2f} |",
        f"| expectancy / trade | {m.expectancy_pct:,.3f}% |",
        f"| avg win / avg loss | {m.avg_win_pct:,.2f}% / {m.avg_loss_pct:,.2f}% |",
        f"| avg holding time | {m.avg_bars_held:,.1f} bars |",
        f"| time in market | {m.exposure_pct:,.1f}% |",
        "",
        "## Yearly returns",
        "",
        "| year | return |",
        "| --- | ---: |",
    ]
    for ts, value in yearly_returns(equity).items():
        lines.append(f"| {ts.year} | {value:,.2f}% |")

    stats = signal_stats(trades)
    if len(stats):
        lines += [
            "",
            "## Best entry rules (by realised PnL)",
            "",
            "| rule | trades | win rate | total pnl | avg return |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
        for _, row in stats.iterrows():
            lines.append(
                f"| {row['rule']} | {int(row['trades'])} | {row['win_rate_pct']:.1f}% |"
                f" {row['total_pnl']:,.2f} | {row['avg_return_pct']:.2f}% |"
            )

    if len(trades):
        exits = (
            trades["exit_reasons"].str.split(",").explode().value_counts().head(10)
        )
        lines += ["", "## Exit reasons", "", "| reason | count |", "| --- | ---: |"]
        for reason, count in exits.items():
            lines.append(f"| {reason} | {count} |")

    lines += ["", "![equity curve](equity_curve.png)", ""]
    return "\n".join(lines)
