from __future__ import annotations

import json

import numpy as np
import pandas as pd

from banksignal.breakout import BreakoutConfig
from banksignal.live import LiveState, format_event, step


def _candles(n: int = 700, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="utc")
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.004, n)))
    spread = np.abs(rng.normal(0, 0.4, n)) + 0.1
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    vol = rng.uniform(50, 150, n)
    return pd.DataFrame(
        {
            "Open": open_,
            "High": np.maximum(open_, close) + spread,
            "Low": np.minimum(open_, close) - spread,
            "Close": close,
            "Volume": vol,
            "TakerBuyBase": vol * rng.uniform(0.3, 0.7, n),
            "Trades": 10,
        },
        index=idx.rename("Time"),
    )


def test_state_round_trip(tmp_path):
    state = LiveState(symbol="BTCUSDT", equity=1.23, trades=4, wins=2, last_bar="x")
    path = tmp_path / "s.json"
    state.save(path)
    loaded = LiveState.load(path)
    assert loaded.equity == 1.23 and loaded.trades == 4 and loaded.last_bar == "x"
    assert loaded.events == []


def test_new_state_starts_in_paper_mode_with_a_week_of_dry_run(tmp_path):
    state = LiveState.load(tmp_path / "missing.json")
    assert state.mode == "paper"
    assert state.paper_until  # a date one week ahead is set


def test_step_processes_only_new_bars(tmp_path):
    candles = _candles()
    cfg = BreakoutConfig(compression_trail=100)
    state = LiveState.load(tmp_path / "s.json")
    state = step(state, candles.iloc[:-5], cfg, tmp_path / "t.csv")
    first_last = state.last_bar
    state.events.clear()
    state = step(state, candles, cfg, tmp_path / "t.csv")
    assert state.last_bar == str(candles.index[-1])
    assert state.last_bar != first_last


def test_positions_open_and_close_and_update_equity(tmp_path):
    candles = _candles(1200, seed=11)
    # force a breakout: a huge candle after a flat stretch
    cfg = BreakoutConfig(
        compression_trail=100,
        body_ratio_min=0.0,
        opposing_wick_max=1.0,
        volume_mult_min=0.0,
        range_width_pctl_max=1.0,
        bad_hours_utc=frozenset(),
        bad_weekday=-1,
        h4_strength_reject_pctl=2.0,
        whale_signal=False,
    )
    state = LiveState.load(tmp_path / "s.json")
    state.last_bar = str(candles.index[300])  # replay the rest of the history
    trades_csv = tmp_path / "trades.csv"
    state = step(state, candles, cfg, trades_csv)
    exits = [e for e in state.events if e["type"] == "exit"]
    entries = [e for e in state.events if e["type"] == "entry"]
    assert entries, "expected at least one paper entry"
    assert state.trades == len(exits)
    if exits:
        assert trades_csv.exists()
        assert state.equity != 1.0


def test_format_event_mentions_paper_mode():
    state = LiveState(mode="paper")
    text = format_event(
        {
            "type": "entry",
            "time": "t",
            "direction": "long",
            "source": "breakout_long",
            "price": 100.0,
            "stop": 95.0,
            "target": 110.0,
        },
        state,
    )
    assert "PAPER" in text and "LONG" in text


def test_saved_state_is_valid_json_without_events(tmp_path):
    state = LiveState()
    state.events.append({"type": "entry"})
    path = tmp_path / "s.json"
    state.save(path)
    data = json.loads(path.read_text())
    assert "events" not in data
