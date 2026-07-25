from __future__ import annotations

import numpy as np
import pandas as pd

from banksignal.breakout import BreakoutConfig, run_breakout, summarise


def _tz(candles: pd.DataFrame) -> pd.DataFrame:
    candles = candles.copy()
    candles.index = candles.index.tz_localize("utc")
    return candles


def test_breakout_runs_and_produces_valid_trades(candles):
    trades = run_breakout(_tz(candles), BreakoutConfig(compression_trail=100))
    assert set(["direction", "entry_price", "exit_price", "ret_pct"]).issubset(trades.columns)
    assert trades["direction"].isin(["long", "short"]).all()
    assert (trades["exit_time"] >= trades["entry_time"]).all()


def test_entries_never_look_ahead():
    """A breakout entry must fill at the open *after* the signal bar."""
    idx = pd.date_range("2024-01-01", periods=600, freq="h", tz="utc")
    close = np.linspace(100, 100, 600)
    close[400:] = 130  # a clean regime shift 400 bars in
    candles = pd.DataFrame(
        {
            "Open": close,
            "High": close * 1.01,
            "Low": close * 0.99,
            "Close": close,
            "Volume": np.full(600, 100.0),
            "TakerBuyBase": np.full(600, 60.0),
            "Trades": 10,
        },
        index=idx,
    ).rename_axis("Time")
    trades = run_breakout(candles, BreakoutConfig(compression_trail=100, allow_short=False))
    assert (trades["entry_time"] > trades["signal_time"]).all()


def test_short_can_be_disabled(candles):
    trades = run_breakout(_tz(candles), BreakoutConfig(compression_trail=100, allow_short=False))
    assert set(trades["direction"]) <= {"long"}


def test_causal_exit_is_not_more_optimistic_than_the_same_bar_variant(candles):
    tz = _tz(candles)
    causal = run_breakout(tz, BreakoutConfig(compression_trail=100, causal_trailing=True))
    optimistic = run_breakout(tz, BreakoutConfig(compression_trail=100, causal_trailing=False))
    # the same-bar lock can only ever help the reported result
    if len(causal) and len(optimistic):
        assert optimistic["ret_pct"].sum() >= causal["ret_pct"].sum() - 1e-9


def test_costs_are_charged_on_every_trade(candles):
    tz = _tz(candles)
    free = run_breakout(tz, BreakoutConfig(compression_trail=100, fee_per_side=0.0, slippage_per_side=0.0))
    costed = run_breakout(tz, BreakoutConfig(compression_trail=100, fee_per_side=0.01, slippage_per_side=0.0))
    if len(free) and len(costed):
        assert costed["ret_pct"].mean() < free["ret_pct"].mean()


def test_summary_splits_train_and_test(candles):
    trades = run_breakout(_tz(candles), BreakoutConfig(compression_trail=100))
    report = summarise(trades, candles.index[300])
    assert report.metrics["train"]["trades"] + report.metrics["test"]["trades"] == len(trades)
