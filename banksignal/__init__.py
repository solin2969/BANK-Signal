"""BANK-Signal: a trading system driven by the ``bank.csv`` signal reference."""

from .backtest import BacktestConfig, Backtester, BacktestResult
from .data import load_candles, slice_period
from .engine import EngineConfig, EngineOutput, SignalEngine
from .features import FeatureConfig, build_features
from .metrics import Metrics, compute_metrics
from .rules import Rule, load_rules, parse_rules

__all__ = [
    "BacktestConfig",
    "BacktestResult",
    "Backtester",
    "EngineConfig",
    "EngineOutput",
    "FeatureConfig",
    "Metrics",
    "Rule",
    "SignalEngine",
    "build_features",
    "compute_metrics",
    "load_candles",
    "load_rules",
    "parse_rules",
    "slice_period",
]
