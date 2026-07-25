"""Signal quality measurement and rule selection.

Two questions are answered here, both independently of the backtester:

1. *Does a rule predict anything?* For every horizon the forward return after
   the rule fired is compared with the unconditional forward return of the same
   window, in the direction the rule claims (``LONG`` up, ``SHORT``/``EXIT*``
   down). The difference is the **edge**, in percentage points per trade.
2. *Is the edge real?* The edge is scored with a t-statistic and, crucially,
   only measured on the selection window. Rules are then kept or dropped by
   :func:`select_rules`, and the kept set is validated on data that was never
   used for the selection.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .engine import EXIT_ACTIONS, LONG_ACTIONS, SHORT_ACTIONS, SignalEngine
from .rules import Rule

DEFAULT_HORIZONS = (6, 24, 72)


@dataclass(frozen=True)
class QualityConfig:
    horizons: tuple[int, ...] = DEFAULT_HORIZONS
    min_signals: int = 100  # too few signals -> the edge cannot be measured
    max_frequency: float = 0.35  # a rule firing on >35% of bars carries no information
    min_edge: float = 0.02  # percentage points per horizon, after costs
    min_tstat: float = 1.5
    min_positive_horizons: int = 2  # the edge must survive several holding times


def rule_direction(rule: Rule) -> int:
    """+1 if the rule expects the price to rise, -1 if it expects a fall, else 0."""
    if rule.action in LONG_ACTIONS:
        return 1
    if rule.action in SHORT_ACTIONS:
        return -1
    if rule.action == "EXIT" or rule.action in EXIT_ACTIONS:
        return -1  # an exit claims the move in the trade's favour is over
    return 0


def forward_returns(close: pd.Series, horizon: int) -> pd.Series:
    return (close.shift(-horizon) / close - 1.0) * 100.0


def rule_quality(
    engine: SignalEngine,
    fired: pd.DataFrame,
    close: pd.Series,
    cfg: QualityConfig | None = None,
) -> pd.DataFrame:
    """One row per rule with its edge, t-stat and hit rate at every horizon."""
    cfg = cfg or QualityConfig()
    n_bars = len(close)
    rows = []
    for rule in engine.rules:
        direction = rule_direction(rule)
        if direction == 0 or rule.name not in fired.columns:
            continue
        mask = fired[rule.name].to_numpy(dtype=bool)
        row: dict[str, object] = {
            "rule": rule.name,
            "action": rule.action,
            "phase": rule.phase,
            "signals": int(mask.sum()),
            "frequency": float(mask.mean()),
        }
        positive = 0
        edges = []
        for hz in cfg.horizons:
            fwd = forward_returns(close, hz)
            valid = mask & fwd.notna().to_numpy()
            sample = fwd.to_numpy()[valid]
            baseline = float(fwd.mean())
            if len(sample) < 2:
                row[f"edge_{hz}h"] = np.nan
                row[f"t_{hz}h"] = np.nan
                row[f"hit_{hz}h"] = np.nan
                continue
            edge = direction * (float(sample.mean()) - baseline)
            tstat = edge / (sample.std(ddof=1) / np.sqrt(len(sample)) or np.nan)
            row[f"edge_{hz}h"] = edge
            row[f"t_{hz}h"] = tstat
            row[f"hit_{hz}h"] = float((direction * (sample - baseline) > 0).mean())
            edges.append(edge)
            if edge >= cfg.min_edge and tstat >= cfg.min_tstat:
                positive += 1
        row["edge_mean"] = float(np.mean(edges)) if edges else np.nan
        row["good_horizons"] = positive
        row["enough_signals"] = row["signals"] >= cfg.min_signals
        row["selective"] = row["frequency"] <= cfg.max_frequency
        row["keep"] = bool(
            row["enough_signals"]
            and row["selective"]
            and positive >= cfg.min_positive_horizons
        )
        row["bars"] = n_bars
        rows.append(row)
    return pd.DataFrame(rows).sort_values("edge_mean", ascending=False).reset_index(drop=True)


def select_rules(quality: pd.DataFrame) -> tuple[set[str], pd.DataFrame]:
    """Return the names of the rules to keep plus a per-rule rejection reason."""
    report = quality.copy()
    report["reason"] = np.where(
        report["keep"],
        "kept",
        np.where(
            ~report["enough_signals"],
            "too few signals",
            np.where(
                ~report["selective"],
                "fires too often",
                "no consistent edge",
            ),
        ),
    )
    return set(report.loc[report["keep"], "rule"]), report


def filter_rule_file(text: str, keep: set[str], drop_directional_only: bool = True) -> str:
    """Rewrite the rule file keeping only ``keep`` (plus the non-directional rules).

    Blocks are copied verbatim, so the filtered file stays a valid rule
    reference that the same parser can execute.
    """
    out: list[str] = []
    block: list[str] = []
    for line in text.splitlines():
        block.append(line)
        if "add_signal(" not in line:
            continue
        name = line.split('"')[1] if '"' in line else ""
        action = line.split('"')[3] if line.count('"') >= 4 else ""
        directional = action in LONG_ACTIONS | SHORT_ACTIONS or action in EXIT_ACTIONS or action == "EXIT"
        if name in keep or (drop_directional_only and not directional):
            out.extend(block)
        block = []
    return "\n".join(out) + "\n"
