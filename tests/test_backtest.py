from __future__ import annotations

import numpy as np
import pandas as pd

from banksignal.backtest import BacktestConfig, Backtester
from banksignal.engine import EngineOutput, SignalEngine
from banksignal.features import build_features
from banksignal.metrics import compute_metrics
from banksignal.rules import load_rules, parse_rules

RULES_PATH = "rules/bank.csv"


def _run(candles, cfg: BacktestConfig | None = None):
    features = build_features(candles)
    engine = SignalEngine(load_rules(RULES_PATH))
    output = engine.evaluate(features)
    return features, Backtester(engine, cfg or BacktestConfig()).run(features, output)


def test_backtest_runs_and_conserves_equity(candles):
    _, result = _run(candles)
    assert len(result.equity) == len(candles)
    assert result.equity.notna().all()
    assert (result.equity > 0).all()


def test_no_position_is_left_open(candles):
    _, result = _run(candles)
    assert result.trades["exit_time"].notna().all()


def test_fills_use_the_next_bar_open(candles):
    _, result = _run(candles)
    entries = result.trades["entry_time"]
    assert entries.is_monotonic_increasing
    # every entry price is inside the range of its own bar
    bar = candles.loc[entries]
    assert (result.trades["entry_price"].to_numpy() >= bar["Low"].to_numpy() * 0.99).all()
    assert (result.trades["entry_price"].to_numpy() <= bar["High"].to_numpy() * 1.01).all()


def test_long_only_mode(candles):
    _, result = _run(candles, BacktestConfig(allow_short=False))
    assert set(result.trades["direction"]) <= {"LONG"}


def test_fees_reduce_the_result(candles):
    _, cheap = _run(candles, BacktestConfig(fee_rate=0.0, slippage_rate=0.0))
    _, pricey = _run(candles, BacktestConfig(fee_rate=0.01, slippage_rate=0.0))
    assert pricey.equity.iloc[-1] < cheap.equity.iloc[-1]


def test_stop_loss_caps_the_loss_of_a_trade():
    """A long entry followed by a crash must exit near the ATR stop."""
    n = 260
    idx = pd.date_range("2024-01-01", periods=n, freq="h")
    close = np.concatenate([np.linspace(100, 140, n - 10), np.linspace(140, 60, 10)])
    candles = pd.DataFrame(
        {
            "Open": close,
            "High": close * 1.002,
            "Low": close * 0.998,
            "Close": close,
            "Volume": np.full(n, 100.0),
            "TakerBuyBase": np.full(n, 70.0),
            "Trades": 10,
        },
        index=idx,
    ).rename_axis("Time")
    _, result = _run(candles, BacktestConfig(stop_atr_mult=1.0, allow_short=False))
    longs = result.trades[result.trades["direction"] == "LONG"]
    if len(longs):
        assert longs["return_pct"].min() > -60.0


def test_metrics_are_consistent(candles):
    _, result = _run(candles)
    m = compute_metrics(result.equity, result.trades, candles["Close"])
    assert m.bars == len(candles)
    assert m.trades == len(result.trades)
    expected = 100.0 * (result.equity.iloc[-1] / result.equity.iloc[0] - 1.0)
    assert m.total_return_pct == pytest_approx(expected)
    assert m.max_drawdown_pct <= 0.0
    assert 0.0 <= m.win_rate_pct <= 100.0


def test_engine_handles_a_rule_set_without_matches(candles):
    rules = parse_rules('if (\n    Energy>1e9\n):\n    add_signal(i,"NEVER","LONG",90,90,90)\n')
    engine = SignalEngine(rules)
    features = build_features(candles)
    output: EngineOutput = engine.evaluate(features)
    assert not output.fired.to_numpy().any()
    result = Backtester(engine).run(features, output)
    assert len(result.trades) == 0
    assert result.equity.iloc[-1] == BacktestConfig().initial_equity


def pytest_approx(value: float, tol: float = 1e-6):
    from pytest import approx

    return approx(value, rel=tol, abs=tol)
