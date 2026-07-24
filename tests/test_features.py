from __future__ import annotations

import numpy as np
import pandas as pd

from banksignal.features import FeatureConfig, build_features


def test_feature_frame_has_no_missing_values(candles):
    f = build_features(candles)
    assert len(f) == len(candles)
    assert not f.isna().any().any()


def test_bounded_features_stay_in_range(candles):
    f = build_features(candles)
    for col in ("BodyRatio", "UpperWick", "LowerWick"):
        assert f[col].between(0, 1).all()
    for col in ("TrendStrength", "TrendScore", "WaveStrength", "ExhaustionScore"):
        assert f[col].between(0, 100).all()
    assert f["TrendDirection"].isin([-1.0, 0.0, 1.0]).all()
    assert set(f["MarketStructure"].unique()) <= {"BULL", "BEAR", "RANGE"}
    assert set(f["MomentumCycle"].unique()) <= {"START", "MID", "END", "RESET"}
    assert set(f["DNA"].unique()) <= {
        "TREND",
        "ACCUMULATION",
        "DISTRIBUTION",
        "EXHAUSTION",
        "NEUTRAL",
    }


def test_features_are_causal(candles):
    """Truncating the input must not change the features of earlier bars."""
    full = build_features(candles)
    partial = build_features(candles.iloc[:400])
    numeric = [c for c in full.columns if full[c].dtype != object]
    pd.testing.assert_frame_equal(
        full[numeric].iloc[:400], partial[numeric], check_exact=False, rtol=1e-9
    )


def test_history_levels_exclude_the_current_bar(candles):
    f = build_features(candles)
    highs = candles["High"].rolling(200, min_periods=20).max().shift(1)
    assert np.allclose(f["HistoryHigh200"].iloc[250:], highs.iloc[250:])


def test_whale_detection_reacts_to_volume_spikes(candles):
    spiked = candles.copy()
    spiked.iloc[500, spiked.columns.get_loc("Volume")] *= 30
    spiked.iloc[500, spiked.columns.get_loc("TakerBuyBase")] = (
        spiked.iloc[500]["Volume"] * 0.95
    )
    f = build_features(spiked)
    assert bool(f["WhaleBuy"].iloc[500])
    assert not bool(build_features(candles)["WhaleBuy"].iloc[500])


def test_config_thresholds_are_applied(candles):
    strict = build_features(candles, FeatureConfig(whale_volume_mult=100.0))
    assert not strict["WhaleBuy"].any()
