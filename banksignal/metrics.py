"""Performance statistics for a backtest run."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

BARS_PER_YEAR = 24 * 365  # 1h candles


@dataclass
class Metrics:
    start: str
    end: str
    bars: int
    initial_equity: float
    final_equity: float
    total_return_pct: float
    cagr_pct: float
    max_drawdown_pct: float
    sharpe: float
    sortino: float
    calmar: float
    trades: int
    win_rate_pct: float
    profit_factor: float
    expectancy_pct: float
    avg_win_pct: float
    avg_loss_pct: float
    avg_bars_held: float
    long_trades: int
    short_trades: int
    exposure_pct: float
    buy_hold_return_pct: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def compute_metrics(
    equity: pd.Series, trades: pd.DataFrame, price: pd.Series, bars_per_year: int = BARS_PER_YEAR
) -> Metrics:
    equity = equity.dropna()
    returns = equity.pct_change().fillna(0.0)
    years = max(len(equity) / bars_per_year, 1e-9)

    total_return = 100.0 * (equity.iloc[-1] / equity.iloc[0] - 1.0)
    cagr = 100.0 * ((equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1.0)
    drawdown = equity / equity.cummax() - 1.0
    max_dd = 100.0 * drawdown.min()

    std = returns.std(ddof=0)
    downside = returns[returns < 0].std(ddof=0)
    ann = np.sqrt(bars_per_year)
    sharpe = float(returns.mean() / std * ann) if std > 0 else 0.0
    sortino = float(returns.mean() / downside * ann) if downside and downside > 0 else 0.0
    calmar = float(cagr / abs(max_dd)) if max_dd < 0 else 0.0

    closed = trades[trades["exit_time"].notna()] if len(trades) else trades
    wins = closed[closed["pnl"] > 0] if len(closed) else closed
    losses = closed[closed["pnl"] <= 0] if len(closed) else closed
    gross_win = float(wins["pnl"].sum()) if len(wins) else 0.0
    gross_loss = float(-losses["pnl"].sum()) if len(losses) else 0.0

    exposure = 0.0
    if len(closed):
        exposure = 100.0 * float(closed["bars"].sum()) / max(len(equity), 1)

    return Metrics(
        start=str(equity.index[0]),
        end=str(equity.index[-1]),
        bars=int(len(equity)),
        initial_equity=float(equity.iloc[0]),
        final_equity=float(equity.iloc[-1]),
        total_return_pct=float(total_return),
        cagr_pct=float(cagr),
        max_drawdown_pct=float(max_dd),
        sharpe=sharpe,
        sortino=sortino,
        calmar=calmar,
        trades=int(len(closed)),
        win_rate_pct=float(100.0 * len(wins) / len(closed)) if len(closed) else 0.0,
        profit_factor=float(gross_win / gross_loss) if gross_loss > 0 else float("inf"),
        expectancy_pct=float(closed["return_pct"].mean()) if len(closed) else 0.0,
        avg_win_pct=float(wins["return_pct"].mean()) if len(wins) else 0.0,
        avg_loss_pct=float(losses["return_pct"].mean()) if len(losses) else 0.0,
        avg_bars_held=float(closed["bars"].mean()) if len(closed) else 0.0,
        long_trades=int((closed["direction"] == "LONG").sum()) if len(closed) else 0,
        short_trades=int((closed["direction"] == "SHORT").sum()) if len(closed) else 0,
        exposure_pct=exposure,
        buy_hold_return_pct=float(100.0 * (price.iloc[-1] / price.iloc[0] - 1.0)),
    )


def yearly_returns(equity: pd.Series) -> pd.Series:
    """Calendar-year percentage returns of the equity curve."""
    yearly = equity.resample("YE").last()
    first = pd.Series([equity.iloc[0]], index=[equity.index[0]])
    joined = pd.concat([first, yearly])
    return (joined.pct_change().dropna() * 100.0).rename("return_pct")


def signal_stats(trades: pd.DataFrame, top: int = 15) -> pd.DataFrame:
    """Per entry-rule performance, ranked by total PnL."""
    if not len(trades):
        return pd.DataFrame(columns=["rule", "trades", "win_rate_pct", "total_pnl"])
    rows = []
    exploded = trades.assign(rule=trades["entry_reasons"].str.split(",")).explode("rule")
    exploded = exploded[exploded["rule"].astype(bool)]
    for rule, grp in exploded.groupby("rule"):
        rows.append(
            {
                "rule": rule,
                "trades": len(grp),
                "win_rate_pct": 100.0 * float((grp["pnl"] > 0).mean()),
                "total_pnl": float(grp["pnl"].sum()),
                "avg_return_pct": float(grp["return_pct"].mean()),
            }
        )
    return (
        pd.DataFrame(rows)
        .sort_values("total_pnl", ascending=False)
        .head(top)
        .reset_index(drop=True)
    )
