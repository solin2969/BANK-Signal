from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from banksignal.engine import SignalEngine
from banksignal.quality import (
    QualityConfig,
    filter_rule_file,
    forward_returns,
    rule_direction,
    rule_quality,
    select_rules,
)
from banksignal.rules import load_rules, parse_rules

RULE_TEXT = (
    'if (\n    Delta>0\n):\n    add_signal(i,"GOOD_LONG","LONG",95,95,95)\n'
    'if (\n    Delta<0\n):\n    add_signal(i,"BAD_LONG","LONG",95,95,95)\n'
    'if (\n    Energy>0\n):\n    add_signal(i,"ALWAYS","LONG",95,95,95)\n'
    'if (\n    Energy>1e9\n):\n    add_signal(i,"NEVER","LONG",95,95,95)\n'
    'if (\n    Delta>0\n):\n    add_signal(i,"NOTE","AUTO",95,95,95)\n'
)


def _fired_frame(n: int = 2000) -> tuple[pd.DataFrame, pd.Series]:
    """A signal that predicts the next moves, one that predicts the opposite."""
    rng = np.random.default_rng(3)
    idx = pd.date_range("2024-01-01", periods=n, freq="h")
    up = rng.random(n) < 0.2
    down = (~up) & (rng.random(n) < 0.25)
    step = np.where(up, 1.0, 0.0) - np.where(down, 1.0, 0.0) + rng.normal(0, 0.2, n)
    close = pd.Series(100 * np.exp(np.cumsum(step / 100)), index=idx)
    # the signals fire on the bar *before* the move they predict
    good, bad = np.roll(up, -1), np.roll(down, -1)
    good[-1] = bad[-1] = False
    fired = pd.DataFrame(
        {
            "GOOD_LONG": good,
            "BAD_LONG": bad,
            "ALWAYS": np.ones(n, dtype=bool),
            "NEVER": np.zeros(n, dtype=bool),
            "NOTE": good,
        },
        index=idx,
    )
    return fired, close


def test_rule_direction_uses_the_action():
    rules = {r.name: r for r in load_rules("rules/bank.csv")}
    assert rule_direction(rules["FIB_236_LONG"]) == 1
    assert rule_direction(rules["FIB_236_SHORT"]) == -1
    assert rule_direction(rules["MASTER_EXIT_ALL"]) == -1
    assert rule_direction(rules["MOMENTUM_START"]) == 0


def test_forward_returns_are_shifted_backwards():
    close = pd.Series([100.0, 110.0, 121.0])
    fwd = forward_returns(close, 1)
    assert fwd.iloc[0] == pytest.approx(10.0)
    assert np.isnan(fwd.iloc[-1])


def test_quality_separates_predictive_from_useless_rules():
    engine = SignalEngine(parse_rules(RULE_TEXT))
    fired, close = _fired_frame()
    quality = rule_quality(
        engine, fired, close, QualityConfig(horizons=(6, 24), min_positive_horizons=2)
    )
    by_rule = quality.set_index("rule")

    assert "NOTE" not in by_rule.index  # non-directional rules are not scored
    assert by_rule.loc["GOOD_LONG", "keep"]
    assert not by_rule.loc["BAD_LONG", "keep"]
    assert not by_rule.loc["ALWAYS", "keep"]
    assert not by_rule.loc["NEVER", "keep"]
    assert by_rule.loc["GOOD_LONG", "edge_6h"] > by_rule.loc["BAD_LONG", "edge_6h"]


def test_rejection_reasons_are_explicit():
    engine = SignalEngine(parse_rules(RULE_TEXT))
    fired, close = _fired_frame()
    _, report = select_rules(rule_quality(engine, fired, close, QualityConfig()))
    reasons = report.set_index("rule")["reason"]
    assert reasons["NEVER"] == "too few signals"
    assert reasons["ALWAYS"] == "fires too often"
    assert reasons["BAD_LONG"] == "no consistent edge"


def test_filtered_file_keeps_selected_and_non_directional_rules():
    filtered = filter_rule_file(RULE_TEXT, {"GOOD_LONG"})
    names = {r.name for r in parse_rules(filtered)}
    assert names == {"GOOD_LONG", "NOTE"}


def test_filtered_reference_file_stays_parsable():
    text = open("rules/bank.csv", encoding="utf-8").read()
    keep = {"SUPPORT_MAJOR", "EARLY_WAVE_LONG"}
    rules = parse_rules(filter_rule_file(text, keep))
    directional = {r.name for r in rules if rule_direction(r) != 0}
    assert directional == keep
