from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from banksignal.engine import SignalEngine
from banksignal.rules import (
    PHASE_MARKET,
    PHASE_POSITION,
    PHASE_SCORE,
    RuleParseError,
    load_rules,
    parse_rules,
    required_variables,
)

RULES_PATH = "rules/bank.csv"


def test_reference_file_parses_completely():
    rules = load_rules(RULES_PATH)
    assert len(rules) == 159
    assert {r.phase for r in rules} == {PHASE_MARKET, PHASE_SCORE, PHASE_POSITION}
    assert all(r.name for r in rules)
    assert all(90 <= r.strength <= 100 for r in rules)


def test_every_variable_is_provided_by_the_engine():
    from banksignal.features import build_features
    from banksignal.rules import POSITION_VARS, SCORE_VARS

    candles = _synthetic_candles(400)
    features = build_features(candles)
    known = set(features.columns) | SCORE_VARS | POSITION_VARS
    assert not required_variables(load_rules(RULES_PATH)) - known


def test_vector_and_scalar_forms_agree():
    rules = load_rules(RULES_PATH)
    rule = next(r for r in rules if r.name == "FIB_236_LONG")
    frame = pd.DataFrame(
        {
            "NearFib236": [True, True, False],
            "Delta": [1.0, -1.0, 1.0],
            "Energy": [5.0, 5.0, 5.0],
            "AvgEnergy": [1.0, 1.0, 1.0],
        }
    )
    vector = eval(rule.vector_code, {"__builtins__": {}}, dict(frame.items()))
    scalar = [
        bool(eval(rule.scalar_code, {"__builtins__": {}}, frame.iloc[i].to_dict()))
        for i in range(len(frame))
    ]
    assert list(vector) == scalar == [True, False, False]


def test_string_comparisons_are_supported():
    rules = parse_rules(
        'if (\n    DNA=="TREND"\n    and\n    BodyRatio>0.70\n):\n'
        '    add_signal(i,"X","AUTO",92,92,92)\n'
    )
    frame = {"DNA": pd.Series(["TREND", "RANGE"]), "BodyRatio": pd.Series([0.8, 0.9])}
    assert list(eval(rules[0].vector_code, {"__builtins__": {}}, frame)) == [True, False]


def test_malformed_rule_is_rejected():
    with pytest.raises(RuleParseError):
        parse_rules("if (A):\n    other_call(1)\n")


def test_phase_classification():
    rules = {r.name: r for r in load_rules(RULES_PATH)}
    assert rules["FIB_236_LONG"].phase == PHASE_MARKET
    assert rules["MASTER_LONG"].phase == PHASE_SCORE
    assert rules["TRAIL_WHALE"].phase == PHASE_POSITION


def test_engine_splits_rules_by_phase():
    engine = SignalEngine(load_rules(RULES_PATH))
    assert len(engine.market_rules) + len(engine.score_rules) + len(
        engine.position_rules
    ) == len(engine.rules)
    assert engine.position_rules


def _synthetic_candles(n: int) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    idx = pd.date_range("2024-01-01", periods=n, freq="h")
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    high = close + rng.random(n)
    low = close - rng.random(n)
    volume = rng.random(n) * 100 + 10
    return pd.DataFrame(
        {
            "Open": close + rng.normal(0, 0.2, n),
            "High": np.maximum(high, close),
            "Low": np.minimum(low, close),
            "Close": close,
            "Volume": volume,
            "TakerBuyBase": volume * rng.random(n),
            "Trades": 10,
        },
        index=idx,
    ).rename_axis("Time")
