"""Feature engine.

Every variable referenced by ``rules/bank.csv`` is produced here, so the rule
file can be evaluated verbatim against a feature frame. Variables fall into two
groups:

* market features (this module) - derived from OHLCV + taker-buy volume;
* runtime features (``engine``/``backtest``) - scores, signal counts and
  ``Profit``, which depend on the rule evaluation itself or on an open
  position.

Naming of the columns matches the identifiers used in the rule file exactly.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

FIB_LEVELS = {
    "NearFib236": 0.236,
    "NearFib382": 0.382,
    "NearFib500": 0.500,
    "NearFib618": 0.618,
    "NearFib786": 0.786,
}


@dataclass(frozen=True)
class FeatureConfig:
    """Tunable thresholds of the feature engine."""

    atr_period: int = 14
    energy_avg_period: int = 50
    volume_avg_period: int = 50
    swing_window: int = 5
    trend_fast: int = 50
    trend_slow: int = 200
    whale_volume_mult: float = 3.0
    whale_pressure: float = 0.10
    whale_memory: int = 24
    fib_tolerance_atr: float = 0.35
    level_tolerance_atr: float = 0.50
    barrier_range_atr: float = 1.0
    touches_for_full_strength: int = 6
    flat_atr: float = 0.20
    compression_atr: float = 0.60
    bos_window: int = 10
    slope_window: int = 3


def build_features(df: pd.DataFrame, cfg: FeatureConfig | None = None) -> pd.DataFrame:
    """Return a frame with one column per market variable used by the rules."""
    cfg = cfg or FeatureConfig()
    f = pd.DataFrame(index=df.index)

    o, h, low, c, v = (df["Open"], df["High"], df["Low"], df["Close"], df["Volume"])
    f["Open"], f["High"], f["Low"], f["Close"], f["Volume"] = o, h, low, c, v

    atr = _atr(h, low, c, cfg.atr_period)
    f["ATR"] = atr
    rng = (h - low).replace(0.0, np.nan)

    _candle_dna(f, o, h, low, c, rng)
    _order_flow(f, df, v, cfg)
    _energy(f, rng, atr, v, cfg)
    _trend(f, c, atr, cfg)
    _levels(f, h, low, c, atr, cfg)
    _structure(f, h, low, c, atr, cfg)
    _whales(f, v, cfg)
    _liquidity(f, h, low, c, o, v, rng, atr, cfg)
    _regime(f, c, atr, rng, v, cfg)
    _composites(f, cfg)

    return f.replace([np.inf, -np.inf], np.nan).fillna(_fill_values(f))


# --------------------------------------------------------------------------- #
# candle anatomy
# --------------------------------------------------------------------------- #
def _candle_dna(
    f: pd.DataFrame,
    o: pd.Series,
    h: pd.Series,
    low: pd.Series,
    c: pd.Series,
    rng: pd.Series,
) -> None:
    body = (c - o).abs()
    f["BodyRatio"] = (body / rng).fillna(0.0)
    f["UpperWick"] = ((h - np.maximum(o, c)) / rng).fillna(0.0)
    f["LowerWick"] = ((np.minimum(o, c) - low) / rng).fillna(0.0)
    f["UpperWickDominant"] = f["UpperWick"] > (f["LowerWick"] + f["BodyRatio"])
    f["LowerWickDominant"] = f["LowerWick"] > (f["UpperWick"] + f["BodyRatio"])
    f["Bullish"] = c > o


# --------------------------------------------------------------------------- #
# order flow: delta / pressure
# --------------------------------------------------------------------------- #
def _order_flow(
    f: pd.DataFrame, df: pd.DataFrame, v: pd.Series, cfg: FeatureConfig
) -> None:
    buy = df["TakerBuyBase"]
    sell = v - buy
    delta = buy - sell
    avg_vol = v.rolling(cfg.volume_avg_period, min_periods=5).mean()

    f["Delta"] = delta / avg_vol.replace(0.0, np.nan)  # normalised by average volume
    f["DeltaSlope"] = _slope(f["Delta"], cfg.slope_window)
    f["DeltaAcceleration"] = f["DeltaSlope"].diff()
    f["DeltaIncreasing"] = f["DeltaSlope"] > 0
    f["DeltaDecreasing"] = f["DeltaSlope"] < 0
    f["DeltaFlat"] = f["DeltaSlope"].abs() < 0.05

    pressure = (delta / v.replace(0.0, np.nan)).fillna(0.0)  # -1 .. 1
    f["Pressure"] = pressure
    f["PressureSlope"] = _slope(pressure, cfg.slope_window)
    f["PressureIncreasing"] = f["PressureSlope"] > 0

    f["VolumeRatio"] = v / avg_vol.replace(0.0, np.nan)
    f["VolumeIncreasing"] = v > v.shift(1)
    f["VolumeFlat"] = (f["VolumeRatio"] - 1.0).abs() < 0.10

    f["DeltaRecovery"] = (f["Delta"] > 0) & (f["Delta"].shift(1) <= 0)
    f["PressureRecovery"] = (pressure > 0) & (pressure.shift(1) <= 0)


# --------------------------------------------------------------------------- #
# energy
# --------------------------------------------------------------------------- #
def _energy(
    f: pd.DataFrame, rng: pd.Series, atr: pd.Series, v: pd.Series, cfg: FeatureConfig
) -> None:
    energy = (rng / atr.replace(0.0, np.nan)).fillna(0.0) * f["VolumeRatio"].fillna(1.0)
    f["Energy"] = energy
    f["AvgEnergy"] = energy.rolling(cfg.energy_avg_period, min_periods=5).mean()
    f["EnergySlope"] = _slope(energy, cfg.slope_window)
    f["EnergyAcceleration"] = f["EnergySlope"].diff()
    f["HighestEnergy50"] = energy.rolling(50, min_periods=5).max().shift(1)
    f["HighestEnergy100"] = energy.rolling(100, min_periods=5).max().shift(1)

    f["EnergyDecreasing"] = f["EnergySlope"] < 0
    f["EnergyFlat"] = f["EnergySlope"].abs() < 0.05
    f["EnergyWeakening"] = (f["EnergySlope"] < 0) & (energy < f["AvgEnergy"])
    f["EnergyRecovering"] = (f["EnergySlope"] > 0) & (energy > f["AvgEnergy"])
    f["EnergyRecovery"] = (energy > f["AvgEnergy"]) & (
        energy.shift(1) <= f["AvgEnergy"].shift(1)
    )
    f["EnergyCollapse"] = energy < (0.35 * f["AvgEnergy"])
    f["FlashEnergyCollapse"] = (energy < 0.30 * energy.shift(1)) & (
        energy.shift(1) > f["AvgEnergy"].shift(1)
    )
    f["EnergySignal"] = (energy > f["AvgEnergy"]) & (f["EnergySlope"] > 0)
    f["DeltaSignal"] = (f["Delta"] > 0) & f["DeltaIncreasing"]
    f["PressureSignal"] = (f["Pressure"] > 0) & f["PressureIncreasing"]


# --------------------------------------------------------------------------- #
# trend
# --------------------------------------------------------------------------- #
def _trend(f: pd.DataFrame, c: pd.Series, atr: pd.Series, cfg: FeatureConfig) -> None:
    ema_fast = c.ewm(span=cfg.trend_fast, adjust=False).mean()
    ema_slow = c.ewm(span=cfg.trend_slow, adjust=False).mean()
    spread = (ema_fast - ema_slow) / atr.replace(0.0, np.nan)

    f["EmaFast"], f["EmaSlow"] = ema_fast, ema_slow
    f["TrendDirection"] = np.sign(spread).fillna(0.0)
    f["TrendStrength"] = (spread.abs() / 3.0).clip(0, 1).fillna(0.0) * 100.0
    f["TrendSlope"] = _slope(ema_fast, cfg.slope_window) / atr.replace(0.0, np.nan)

    aligned = (np.sign(f["TrendSlope"]) == f["TrendDirection"]).astype(float)
    f["TrendScore"] = (0.6 * f["TrendStrength"] + 40.0 * aligned).clip(0, 100)
    f["MomentumCycle"] = _momentum_cycle(f)


def _momentum_cycle(f: pd.DataFrame) -> pd.Series:
    """Classify where the current momentum impulse is in its life cycle."""
    strength, slope, energy_slope = f["TrendStrength"], f["TrendSlope"], f["EnergySlope"]
    cycle = pd.Series("RESET", index=f.index, dtype=object)
    cycle[(strength > 20) & (slope.abs() > 0) & (energy_slope > 0)] = "START"
    cycle[(strength > 50) & (energy_slope <= 0)] = "MID"
    cycle[(strength > 70) & (energy_slope < 0)] = "END"
    return cycle


# --------------------------------------------------------------------------- #
# historical levels
# --------------------------------------------------------------------------- #
def _levels(
    f: pd.DataFrame,
    h: pd.Series,
    low: pd.Series,
    c: pd.Series,
    atr: pd.Series,
    cfg: FeatureConfig,
) -> None:
    tol = cfg.level_tolerance_atr * atr
    for window in (200, 1000):
        hi = h.rolling(window, min_periods=20).max().shift(1)
        lo = low.rolling(window, min_periods=20).min().shift(1)
        f[f"HistoryHigh{window}"] = hi
        f[f"HistoryLow{window}"] = lo
        f[f"NearHistoryHigh{window}"] = (c - hi).abs() <= tol
        f[f"NearHistoryLow{window}"] = (c - lo).abs() <= tol


# --------------------------------------------------------------------------- #
# swing structure, BOS, fibonacci, waves, barriers
# --------------------------------------------------------------------------- #
def _structure(  # noqa: C901 - single pass over bars keeps the state machine local
    f: pd.DataFrame,
    h: pd.Series,
    low: pd.Series,
    c: pd.Series,
    atr: pd.Series,
    cfg: FeatureConfig,
) -> None:
    n = len(f)
    w = cfg.swing_window
    high, lo_, close, atr_v = h.to_numpy(), low.to_numpy(), c.to_numpy(), atr.to_numpy()

    cols = {
        name: np.zeros(n, dtype=bool)
        for name in (
            "SwingHighConfirmed",
            "SwingLowConfirmed",
            "HigherHighDetected",
            "HigherLowDetected",
            "LowerHighDetected",
            "LowerLowDetected",
            "NearSwingHigh",
            "NearSwingLow",
            "SwingBrokenUp",
            "SwingBrokenDown",
            "BOSUp",
            "BOSDown",
            "BOSRetestBull",
            "BOSRetestBear",
            "BOSFailureBull",
            "BOSFailureBear",
            "FiboFailure",
            "WaveFailure",
            *FIB_LEVELS,
        )
    }
    swing_high = np.full(n, np.nan)
    swing_low = np.full(n, np.nan)
    wave_position = np.zeros(n)
    wave_strength = np.zeros(n)
    market_structure = np.empty(n, dtype=object)

    last_high = last_low = np.nan
    prev_high = prev_low = np.nan
    leg_start = np.nan
    leg_dir = 0
    prev_leg_len = np.nan
    wave_peak = 0.0
    structure = "RANGE"
    bos_dir = 0  # +1 after a bullish break, -1 after a bearish break
    bos_level = np.nan
    bos_age = 0
    bos_retested = False

    for i in range(n):
        tol = cfg.level_tolerance_atr * (atr_v[i] if atr_v[i] > 0 else 1e-9)

        # --- fractal pivots confirmed w bars later ---------------------------
        p = i - w
        if p - w >= 0:
            seg_h = high[p - w : p + w + 1]
            seg_l = lo_[p - w : p + w + 1]
            if high[p] == seg_h.max() and high[p] >= high[p - w : p].max():
                cols["SwingHighConfirmed"][i] = True
                prev_high, last_high = last_high, high[p]
                if not np.isnan(prev_high):
                    if last_high > prev_high:
                        cols["HigherHighDetected"][i] = True
                    elif last_high < prev_high:
                        cols["LowerHighDetected"][i] = True
                if leg_dir >= 0:
                    prev_leg_len = (
                        abs(last_high - leg_start) if not np.isnan(leg_start) else np.nan
                    )
                leg_start, leg_dir, wave_peak = last_high, -1, 0.0
            if lo_[p] == seg_l.min() and lo_[p] <= lo_[p - w : p].min():
                cols["SwingLowConfirmed"][i] = True
                prev_low, last_low = last_low, lo_[p]
                if not np.isnan(prev_low):
                    if last_low > prev_low:
                        cols["HigherLowDetected"][i] = True
                    elif last_low < prev_low:
                        cols["LowerLowDetected"][i] = True
                if leg_dir <= 0:
                    prev_leg_len = (
                        abs(leg_start - last_low) if not np.isnan(leg_start) else np.nan
                    )
                leg_start, leg_dir, wave_peak = last_low, 1, 0.0

        swing_high[i], swing_low[i] = last_high, last_low
        cols["NearSwingHigh"][i] = (
            not np.isnan(last_high) and abs(close[i] - last_high) <= tol
        )
        cols["NearSwingLow"][i] = (
            not np.isnan(last_low) and abs(close[i] - last_low) <= tol
        )

        # --- market structure ------------------------------------------------
        if cols["HigherHighDetected"][i] or cols["HigherLowDetected"][i]:
            structure = "BULL"
        elif cols["LowerLowDetected"][i] or cols["LowerHighDetected"][i]:
            structure = "BEAR"
        market_structure[i] = structure

        # --- break of structure ----------------------------------------------
        broke_up = not np.isnan(last_high) and close[i] > last_high
        broke_down = not np.isnan(last_low) and close[i] < last_low
        cols["SwingBrokenUp"][i] = broke_up
        cols["SwingBrokenDown"][i] = broke_down
        if broke_up and bos_dir != 1:
            cols["BOSUp"][i] = True
            bos_dir, bos_level, bos_age, bos_retested = 1, last_high, 0, False
        elif broke_down and bos_dir != -1:
            cols["BOSDown"][i] = True
            bos_dir, bos_level, bos_age, bos_retested = -1, last_low, 0, False
        elif bos_dir != 0:
            bos_age += 1
            if bos_age <= cfg.bos_window:
                if bos_dir == 1:
                    if not bos_retested and abs(lo_[i] - bos_level) <= tol:
                        bos_retested = True
                    elif bos_retested and close[i] > bos_level:
                        cols["BOSRetestBull"][i] = True
                        bos_retested = False
                    if close[i] < bos_level - tol:
                        cols["BOSFailureBull"][i] = True
                        bos_dir = 0
                else:
                    if not bos_retested and abs(high[i] - bos_level) <= tol:
                        bos_retested = True
                    elif bos_retested and close[i] < bos_level:
                        cols["BOSRetestBear"][i] = True
                        bos_retested = False
                    if close[i] > bos_level + tol:
                        cols["BOSFailureBear"][i] = True
                        bos_dir = 0

        # --- fibonacci retracement of the last completed leg -------------------
        if not np.isnan(last_high) and not np.isnan(last_low) and last_high > last_low:
            span = last_high - last_low
            fib_tol = cfg.fib_tolerance_atr * (atr_v[i] if atr_v[i] > 0 else 1e-9)
            for name, ratio in FIB_LEVELS.items():
                level = (
                    last_high - span * ratio if leg_dir <= 0 else last_low + span * ratio
                )
                cols[name][i] = abs(close[i] - level) <= fib_tol
            invalidation = last_high - span * 1.0
            cols["FiboFailure"][i] = close[i] < invalidation - fib_tol

        # --- wave position inside the running leg ------------------------------
        if not np.isnan(leg_start) and leg_dir != 0:
            target = prev_leg_len if not np.isnan(prev_leg_len) and prev_leg_len > 0 else None
            move = (close[i] - leg_start) * leg_dir
            if target:
                wave_position[i] = float(np.clip(move / target, 0.0, 1.5))
            atr_i = atr_v[i] if atr_v[i] > 0 else np.nan
            wave_strength[i] = float(np.clip(move / (3.0 * atr_i), 0.0, 1.0) * 100.0) if atr_i else 0.0
            if wave_position[i] > wave_peak:
                wave_peak = wave_position[i]
            elif wave_peak > 0.6 and wave_position[i] < 0.2:
                cols["WaveFailure"][i] = True
                wave_peak = 0.0

    for name, arr in cols.items():
        f[name] = arr
    f["SwingHigh"] = swing_high
    f["SwingLow"] = swing_low
    f["WavePosition"] = wave_position
    f["WaveStrength"] = wave_strength
    f["WaveAcceleration"] = f["WaveStrength"].diff().fillna(0.0)
    f["WaveSignal"] = f["WaveStrength"] > 60
    f["MarketStructure"] = pd.Series(market_structure, index=f.index).fillna("RANGE")
    f["BOSFailure"] = f["BOSFailureBull"] | f["BOSFailureBear"]
    f["StructureFailure"] = ((f["TrendDirection"] > 0) & f["SwingBrokenDown"]) | (
        (f["TrendDirection"] < 0) & f["SwingBrokenUp"]
    )
    f["StructureAcceleration"] = f["TrendStrength"].diff().fillna(0.0) > 5
    f["StructureWeakening"] = f["TrendStrength"].diff().fillna(0.0) < -5
    f["PullbackFinished"] = (
        (f["WavePosition"] < 0.35)
        & (f["TrendDirection"] > 0)
        & (f["Close"] > f["Close"].shift(1))
    )


# --------------------------------------------------------------------------- #
# whale activity
# --------------------------------------------------------------------------- #
def _whales(f: pd.DataFrame, v: pd.Series, cfg: FeatureConfig) -> None:
    spike = f["VolumeRatio"] > cfg.whale_volume_mult
    f["WhaleBuy"] = spike & (f["Pressure"] > cfg.whale_pressure)
    f["WhaleSell"] = spike & (f["Pressure"] < -cfg.whale_pressure)
    f["WhaleSignal"] = f["WhaleBuy"] | f["WhaleSell"]

    recent_buy = f["WhaleBuy"].rolling(cfg.whale_memory, min_periods=1).max().astype(bool)
    recent_sell = (
        f["WhaleSell"].rolling(cfg.whale_memory, min_periods=1).max().astype(bool)
    )
    f["WhaleStillInside"] = (
        (f["TrendDirection"] > 0) & recent_buy & ~f["WhaleSell"]
    ) | ((f["TrendDirection"] < 0) & recent_sell & ~f["WhaleBuy"])
    f["OppositeWhale"] = ((f["TrendDirection"] > 0) & f["WhaleSell"]) | (
        (f["TrendDirection"] < 0) & f["WhaleBuy"]
    )
    f["WhaleOppositeDetected"] = f["OppositeWhale"]
    f["WhaleExit"] = f["OppositeWhale"] | (f["WhaleSignal"] & (f["EnergySlope"] < 0))


# --------------------------------------------------------------------------- #
# liquidity
# --------------------------------------------------------------------------- #
def _liquidity(
    f: pd.DataFrame,
    h: pd.Series,
    low: pd.Series,
    c: pd.Series,
    o: pd.Series,
    v: pd.Series,
    rng: pd.Series,
    atr: pd.Series,
    cfg: FeatureConfig,
) -> None:
    prior_low = low.rolling(20, min_periods=5).min().shift(1)
    prior_high = h.rolling(20, min_periods=5).max().shift(1)

    f["LiquidityGrabLow"] = (low < prior_low) & (c > prior_low) & (f["Delta"] > 0)
    f["LiquidityGrabHigh"] = (h > prior_high) & (c < prior_high) & (f["Delta"] < 0)
    f["LiquidityAbsorption"] = (f["VolumeRatio"] > 2.0) & (
        rng < 0.6 * atr
    ).fillna(False)
    f["LiquidityVacuum"] = (f["VolumeRatio"] < 0.5) & (rng > 1.5 * atr).fillna(False)
    grabbed = f["LiquidityGrabLow"] | f["LiquidityGrabHigh"]
    reversed_next = np.sign(c - o) != np.sign(c.shift(1) - o.shift(1))
    f["LiquidityTrapDetected"] = grabbed.shift(1).fillna(False).astype(bool) & reversed_next


# --------------------------------------------------------------------------- #
# regime / noise / data quality
# --------------------------------------------------------------------------- #
def _regime(
    f: pd.DataFrame,
    c: pd.Series,
    atr: pd.Series,
    rng: pd.Series,
    v: pd.Series,
    cfg: FeatureConfig,
) -> None:
    direction = f["TrendDirection"]
    flipped = direction != direction.shift(1)
    f["RegimeFlip"] = flipped & (direction != 0)
    f["RegimeFlipConfirmed"] = f["RegimeFlip"].shift(3).fillna(False).astype(bool) & (
        direction == direction.shift(3)
    )

    f["PriceFlat"] = (c - c.shift(3)).abs() < cfg.flat_atr * atr
    compressed = (rng < cfg.compression_atr * atr).fillna(False)
    f["CompressionBars"] = _consecutive(compressed)
    flips = (np.sign(c.diff()) != np.sign(c.diff().shift(1))).rolling(20).sum()
    f["MarketNoise"] = (flips > 13) & (f["TrendStrength"] < 20)
    f["DataQualityLow"] = (v <= 0) | c.isna() | (rng.isna())


# --------------------------------------------------------------------------- #
# composite scores
# --------------------------------------------------------------------------- #
def _composites(f: pd.DataFrame, cfg: FeatureConfig) -> None:
    atr = f["ATR"].replace(0.0, np.nan)
    close = f["Close"]

    levels_above = pd.concat(
        [f["SwingHigh"], f["HistoryHigh200"], f["HistoryHigh1000"]], axis=1
    )
    levels_below = pd.concat(
        [f["SwingLow"], f["HistoryLow200"], f["HistoryLow1000"]], axis=1
    )
    direction = f["TrendDirection"]
    targets = levels_above.where(direction >= 0, levels_below.values)
    distance = (targets.sub(close, axis=0)).abs().div(atr, axis=0)
    within = distance <= cfg.barrier_range_atr

    f["BarrierCount"] = within.sum(axis=1)
    f["BarrierAhead"] = (distance <= 1.0).any(axis=1)
    f["MultiResistance"] = f["BarrierCount"] >= 2
    f["MultiBarrierHit"] = (distance <= 0.25).sum(axis=1) >= 2
    f["BarrierScore"] = (f["BarrierCount"] * 25.0).clip(0, 100)

    per_touch = 100.0 / cfg.touches_for_full_strength
    touches_high = _touch_count(close, f["HistoryHigh200"], atr)
    touches_low = _touch_count(close, f["HistoryLow200"], atr)
    f["ResistanceStrength"] = (touches_high * per_touch).clip(0, 100)
    f["SupportStrength"] = (touches_low * per_touch).clip(0, 100)
    f["ResistanceBroken"] = (close > f["HistoryHigh200"]) & (
        close.shift(1) <= f["HistoryHigh200"].shift(1)
    )
    f["SupportBroken"] = (close < f["HistoryLow200"]) & (
        close.shift(1) >= f["HistoryLow200"].shift(1)
    )

    f["MomentumWeakening"] = (f["EnergySlope"] < 0) & (f["DeltaSlope"] < 0)
    f["ExhaustionScore"] = (
        25.0 * (f["WavePosition"] > 0.8).astype(float)
        + 20.0 * (f["EnergySlope"] < 0).astype(float)
        + 15.0 * (f["DeltaSlope"] < 0).astype(float)
        + 15.0 * f["BarrierAhead"].astype(float)
        + 15.0 * (f["Energy"] > f["HighestEnergy50"]).astype(float)
        + 10.0 * f["WhaleExit"].astype(float)
    ).clip(0, 100)
    f["ExtremeExhaustion"] = f["ExhaustionScore"] > 90
    f["TrendCompletelyFinished"] = (f["WavePosition"] > 0.95) & (f["EnergySlope"] < 0)
    f["DNA"] = _dna(f)


def _dna(f: pd.DataFrame) -> pd.Series:
    """Classify the character of each bar (used by the DNA rule group)."""
    dna = pd.Series("NEUTRAL", index=f.index, dtype=object)
    trending = (f["BodyRatio"] > 0.60) & (f["Energy"] > f["AvgEnergy"])
    compressed = (f["BodyRatio"] < 0.35) & (f["Energy"] < f["AvgEnergy"])
    exhausted = (f["ExhaustionScore"] > 70) & (
        f["UpperWickDominant"] | f["LowerWickDominant"]
    )
    dna[trending] = "TREND"
    dna[compressed & (f["Delta"] > 0)] = "ACCUMULATION"
    dna[compressed & (f["Delta"] < 0)] = "DISTRIBUTION"
    dna[exhausted] = "EXHAUSTION"
    return dna


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _atr(h: pd.Series, low: pd.Series, c: pd.Series, period: int) -> pd.Series:
    prev_close = c.shift(1)
    tr = pd.concat(
        [h - low, (h - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def _slope(series: pd.Series, window: int) -> pd.Series:
    """Average per-bar change over ``window`` bars."""
    return (series - series.shift(window)) / window


def _consecutive(mask: pd.Series) -> pd.Series:
    """Length of the run of True values ending at each bar."""
    grp = (~mask).cumsum()
    return mask.groupby(grp).cumsum().astype(float)


def _touch_count(close: pd.Series, level: pd.Series, atr: pd.Series) -> pd.Series:
    """Number of distinct approaches of ``level`` during the last 200 bars."""
    near = ((close - level).abs() / atr) <= 0.5
    events = near & ~near.shift(1).fillna(False).astype(bool)
    return events.rolling(200, min_periods=1).sum()


def _fill_values(f: pd.DataFrame) -> dict[str, object]:
    fill: dict[str, object] = {}
    for col in f.columns:
        if f[col].dtype == bool:
            fill[col] = False
        elif f[col].dtype == object:
            fill[col] = "RANGE"
        else:
            fill[col] = 0.0
    return fill
