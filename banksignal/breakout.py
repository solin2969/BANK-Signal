"""Compression-breakout strategy with a staircase profit lock.

This is the one configuration in this project that survives out-of-sample. It
is deliberately small: a clean range breakout, taken only when the range was
genuinely compressed, confirmed by volume and a candle-quality filter, with a
soft 4h-trend veto and a set of dead low-liquidity hours removed. Once a trade
is in profit a staircase trailing stop locks most of the favourable excursion,
so a winner is very rarely handed back as a full loss.

Everything is computed from raw OHLCV; no pre-built feature file is needed.
Parameters were calibrated on 2020-2023 and validated untouched on 2024-2026.

The trailing stop is *causal*: the stop active during bar ``j`` is derived only
from data up to bar ``j-1``'s close, so a bar's own high cannot both lock a
profit and then stop the trade out on the same bar (a common backtest
inflation). Removing that optimism costs ~20pp of total return but leaves the
out-of-sample result essentially unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BreakoutConfig:
    lookback: int = 20  # range window that must be broken
    compression_trail: int = 250  # window the range width / avg range is ranked against
    body_ratio_min: float = 0.55  # breakout candle must be decisive
    opposing_wick_max: float = 0.25
    volume_mult_min: float = 1.2
    range_width_pctl_max: float = 0.5  # only the tighter half of ranges
    bad_hours_utc: frozenset[int] = frozenset({0, 19, 20, 21})
    bad_weekday: int = 5  # Saturday
    h4_strength_reject_pctl: float = 0.9  # veto only the strongest 10% opposing 4h trends
    h4_strength_window: int = 500
    hold_bars: int = 10
    rr: float = 2.0
    staircase_tiers: tuple[tuple[float, float], ...] = (
        (0.007, 0.90),
        (0.015, 0.93),
        (0.03, 0.96),
        (0.05, 0.97),
    )
    fee_per_side: float = 0.0005
    slippage_per_side: float = 0.0002
    allow_short: bool = True
    causal_trailing: bool = True  # False reproduces the original same-bar-lock behaviour

    @property
    def round_trip_cost(self) -> float:
        return 2 * (self.fee_per_side + self.slippage_per_side)


TRADE_COLUMNS = [
    "signal_time",
    "entry_time",
    "direction",
    "entry_price",
    "initial_stop",
    "target",
    "exit_price",
    "exit_time",
    "exit_reason",
    "ret_pct",
]


def build_breakout_signals(df: pd.DataFrame, cfg: BreakoutConfig) -> pd.DataFrame:
    d = df.copy()
    rng = d["High"] - d["Low"]
    body = (d["Close"] - d["Open"]).abs()
    upper = d["High"] - d[["Open", "Close"]].max(axis=1)
    lower = d[["Open", "Close"]].min(axis=1) - d["Low"]
    with np.errstate(divide="ignore", invalid="ignore"):
        d["BodyRatio"] = np.where(rng > 0, body / rng, 0.0)
        d["UpperShadowRatio"] = np.where(rng > 0, upper / rng, 0.0)
        d["LowerShadowRatio"] = np.where(rng > 0, lower / rng, 0.0)

    d["roll_high"] = d["High"].shift(1).rolling(cfg.lookback).max()
    d["roll_low"] = d["Low"].shift(1).rolling(cfg.lookback).min()
    d["avg_vol"] = d["Volume"].shift(1).rolling(cfg.lookback).mean()
    avg_range = rng.shift(1).rolling(cfg.lookback).mean()
    d["avg_range"] = avg_range
    d["trail_median_range"] = avg_range.rolling(
        cfg.compression_trail, min_periods=cfg.compression_trail
    ).median()
    width = (d["roll_high"] - d["roll_low"]) / d["roll_low"]
    d["range_width_rank"] = width.rolling(
        cfg.compression_trail, min_periods=cfg.compression_trail
    ).rank(pct=True)

    hour = d.index.hour
    weekday = d.index.weekday
    good_time = (~pd.Index(hour).isin(cfg.bad_hours_utc)) & (weekday != cfg.bad_weekday)
    d["good_time_window"] = np.asarray(good_time)

    h4 = _h4_context(df, cfg)
    d = pd.concat([d, h4], axis=1)
    d["h4_strength_rank"] = d["h4_trend_strength"].rolling(
        cfg.h4_strength_window, min_periods=cfg.h4_strength_window // 2
    ).rank(pct=True)

    compressed = (d["avg_range"] <= d["trail_median_range"]) & (
        d["range_width_rank"] <= cfg.range_width_pctl_max
    )
    quality_long = (d["BodyRatio"] >= cfg.body_ratio_min) & (
        d["LowerShadowRatio"] <= cfg.opposing_wick_max
    )
    quality_short = (d["BodyRatio"] >= cfg.body_ratio_min) & (
        d["UpperShadowRatio"] <= cfg.opposing_wick_max
    )
    volume_ok = d["Volume"] >= cfg.volume_mult_min * d["avg_vol"]

    core_long = (
        (d["Close"] > d["roll_high"] * 1.001)
        & quality_long
        & volume_ok
        & compressed
        & d["good_time_window"]
    )
    core_short = (
        (d["Close"] < d["roll_low"] * 0.999)
        & quality_short
        & volume_ok
        & compressed
        & d["good_time_window"]
    )
    strong_opp = d["h4_strength_rank"] >= cfg.h4_strength_reject_pctl
    reject_long = d["h4_trend_down"].fillna(False) & strong_opp.fillna(False)
    reject_short = d["h4_trend_up"].fillna(False) & strong_opp.fillna(False)

    d["long_signal"] = (core_long & ~reject_long).fillna(False)
    d["short_signal"] = (core_short & ~reject_short).fillna(False)
    if not cfg.allow_short:
        d["short_signal"] = False
    return d


def _h4_context(df: pd.DataFrame, cfg: BreakoutConfig) -> pd.DataFrame:
    h4 = (
        df[["Open", "High", "Low", "Close"]]
        .resample("4h", label="right", closed="right")
        .agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"})
        .dropna()
    )
    ema_fast = h4["Close"].ewm(span=10, adjust=False).mean()
    ema_slow = h4["Close"].ewm(span=30, adjust=False).mean()
    h4["h4_trend_up"] = ema_fast > ema_slow
    h4["h4_trend_down"] = ema_fast < ema_slow
    h4["h4_trend_strength"] = (ema_fast - ema_slow).abs() / ema_slow
    shifted = h4.shift(1)  # only the last fully closed 4h bar
    mapped = shifted.reindex(df.index, method="ffill")
    return mapped[["h4_trend_up", "h4_trend_down", "h4_trend_strength"]]


def _simulate_exit(
    highs, lows, closes, start, entry, stop0, target, direction, cfg
):
    n = len(closes)
    last = min(start + cfg.hold_bars, n - 1)
    cur_stop = stop0
    best_fav = 0.0
    for j in range(start, last + 1):
        hi, lo = highs[j], lows[j]

        if not cfg.causal_trailing:
            fav = (hi - entry) / entry if direction == "long" else (entry - lo) / entry
            cur_stop = _staircase_stop(cur_stop, entry, fav, direction, cfg)

        if direction == "long":
            if lo <= cur_stop:
                return j, cur_stop, ("staircase-lock" if cur_stop != stop0 else "stop")
            if hi >= target:
                return j, target, "target"
        else:
            if hi >= cur_stop:
                return j, cur_stop, ("staircase-lock" if cur_stop != stop0 else "stop")
            if lo <= target:
                return j, target, "target"

        if cfg.causal_trailing:
            fav = (hi - entry) / entry if direction == "long" else (entry - lo) / entry
            best_fav = max(best_fav, fav)
            cur_stop = _staircase_stop(cur_stop, entry, best_fav, direction, cfg)
    return last, closes[last], "time-exit"


def _staircase_stop(
    cur_stop: float, entry: float, fav: float, direction: str, cfg: BreakoutConfig
) -> float:
    locked = 0.0
    for trig, lock_pct in cfg.staircase_tiers:
        if fav >= trig:
            locked = max(locked, lock_pct * fav)
    if locked <= 0:
        return cur_stop
    trail = entry * (1 + locked) if direction == "long" else entry * (1 - locked)
    return max(cur_stop, trail) if direction == "long" else min(cur_stop, trail)


def run_breakout(df: pd.DataFrame, cfg: BreakoutConfig | None = None) -> pd.DataFrame:
    cfg = cfg or BreakoutConfig()
    d = build_breakout_signals(df, cfg)
    highs, lows, closes, opens = (
        d["High"].to_numpy(),
        d["Low"].to_numpy(),
        d["Close"].to_numpy(),
        d["Open"].to_numpy(),
    )
    times = d.index
    long_sig = d["long_signal"].to_numpy()
    short_sig = d["short_signal"].to_numpy()
    roll_high = d["roll_high"].to_numpy()
    roll_low = d["roll_low"].to_numpy()

    n = len(d)
    i = cfg.lookback + cfg.compression_trail
    trades = []
    while i < n - 1:
        entry_idx = i + 1
        direction = "long" if long_sig[i] else "short" if short_sig[i] else None
        if direction is None:
            i += 1
            continue
        entry = opens[entry_idx]
        stop0 = roll_low[i] if direction == "long" else roll_high[i]
        risk = entry - stop0 if direction == "long" else stop0 - entry
        if risk <= 0:
            i += 1
            continue
        target = entry + cfg.rr * risk if direction == "long" else entry - cfg.rr * risk
        ei, ep, reason = _simulate_exit(
            highs, lows, closes, entry_idx, entry, stop0, target, direction, cfg
        )
        gross = (ep / entry - 1) if direction == "long" else (entry / ep - 1)
        trades.append(
            (
                times[i],
                times[entry_idx],
                direction,
                entry,
                stop0,
                target,
                ep,
                times[ei],
                reason,
                gross - cfg.round_trip_cost,
            )
        )
        i = ei
    return pd.DataFrame(trades, columns=TRADE_COLUMNS)


@dataclass
class BreakoutReport:
    trades: pd.DataFrame
    train_end: pd.Timestamp
    metrics: dict = field(default_factory=dict)


def summarise(trades: pd.DataFrame, train_end: str | pd.Timestamp) -> BreakoutReport:
    t = trades.copy()
    t["entry_time"] = pd.to_datetime(t["entry_time"], utc=True)
    t["equity"] = (1 + t["ret_pct"]).cumprod()
    te = pd.Timestamp(train_end)
    te = te.tz_localize("utc") if te.tzinfo is None else te.tz_convert("utc")

    def block(x: pd.DataFrame) -> dict:
        if x.empty:
            return {"trades": 0}
        wins = x.loc[x.ret_pct > 0, "ret_pct"].sum()
        losses = -x.loc[x.ret_pct <= 0, "ret_pct"].sum()
        eq = (1 + x.ret_pct).cumprod()
        return {
            "trades": int(len(x)),
            "win_rate_pct": float((x.ret_pct > 0).mean() * 100),
            "profit_factor": float(wins / losses) if losses > 0 else float("inf"),
            "total_return_pct": float((eq.iloc[-1] - 1) * 100),
            "max_drawdown_pct": float((eq / eq.cummax() - 1).min() * 100),
        }

    metrics = {
        "all": block(t),
        "train": block(t[t.entry_time < te]),
        "test": block(t[t.entry_time >= te]),
        "by_exit": t.exit_reason.value_counts().to_dict(),
    }
    return BreakoutReport(trades=t, train_end=te, metrics=metrics)
