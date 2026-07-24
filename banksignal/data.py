"""OHLCV data loading and normalisation."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

REQUIRED_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


def load_candles(paths: list[str | Path]) -> pd.DataFrame:
    """Load one or more parquet/csv candle files into a single sorted frame.

    The returned frame is indexed by ``Time`` (UTC naive), de-duplicated and
    sorted ascending. ``TakerBuyBase`` is preserved when available because the
    signal engine derives order-flow delta from it.
    """
    if not paths:
        raise ValueError("no data files given")

    frames = [_read_one(Path(p)) for p in paths]
    df = pd.concat(frames, ignore_index=True)

    if "Time" not in df.columns:
        raise ValueError("candle data must contain a 'Time' column")
    df["Time"] = pd.to_datetime(df["Time"], utc=False)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"candle data missing columns: {missing}")

    df = (
        df.drop_duplicates(subset="Time", keep="last")
        .sort_values("Time")
        .set_index("Time")
        .astype({c: "float64" for c in REQUIRED_COLUMNS})
    )
    if "TakerBuyBase" not in df.columns:
        # Without order-flow data, approximate buy volume with the close
        # location value of the bar (Elder's "bar power" proxy).
        rng = (df["High"] - df["Low"]).replace(0.0, pd.NA)
        clv = ((df["Close"] - df["Low"]) / rng).fillna(0.5)
        df["TakerBuyBase"] = df["Volume"] * clv
    if "Trades" not in df.columns:
        df["Trades"] = 0
    return df


def _read_one(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    if path.suffix.lower() in {".csv", ".txt"}:
        return pd.read_csv(path)
    raise ValueError(f"unsupported data file type: {path.suffix}")


def slice_period(
    df: pd.DataFrame, start: str | None = None, end: str | None = None
) -> pd.DataFrame:
    out = df
    if start:
        out = out.loc[out.index >= pd.Timestamp(start)]
    if end:
        out = out.loc[out.index <= pd.Timestamp(end)]
    return out
