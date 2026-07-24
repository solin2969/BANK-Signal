"""Signal engine: evaluates the ``bank.csv`` rules over a feature frame.

Evaluation happens in three phases so that rules which consume aggregated
scores can still be expressed in the same reference file:

1. ``market``   - rules that only touch market features. Evaluated vectorised.
2. ``score``    - rules that read ``EntryScore``/``ExitScore``/``BlockScore``/
   ``SignalCount``/``SignalDensity``. The scores are derived from phase 1, so
   phase 2 sees them as ordinary columns.
3. ``position`` - rules that read ``Profit``/``OppositeSignals``. These depend
   on an open position and are therefore evaluated bar by bar by the
   backtester through :meth:`SignalEngine.evaluate_position_rules`.

Scores are derived from phase 1 only. Feeding phase 2 signals back into the
scores would double count them (``EXIT_Q1`` fires *because* ``ExitScore`` is
high, and would then raise it further), so phase 2 rules only contribute
actions: exit fractions, position sizes, boosts and gates.

Both scores combine their rules as independent confirmations
(``100 * (1 - prod(1 - weight))``) instead of a plain sum, which keeps them
inside 0-100 while still rewarding confluence:

``EntryScore``  weight ``entry_weight * strength/100`` per directional rule of
                the dominant side, minus half of the opposite side;
``ExitScore``   weight ``exit_fraction * strength/100`` per exit rule, so it
                only reaches 100 when a rule with a full exit at full
                confidence fires (the ``EMERGENCY_EXIT``/``FORCE_CLOSE`` band);
``BlockScore``  sum of the strengths of fired ``BLOCK`` rules (0 when none).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from .rules import PHASE_MARKET, PHASE_POSITION, PHASE_SCORE, Rule

EXIT_ACTIONS = {
    "EXIT10": 0.10,
    "EXIT20": 0.20,
    "EXIT25": 0.25,
    "EXIT30": 0.30,
    "EXIT50": 0.50,
    "EXIT75": 0.75,
    "EXIT80": 0.80,
    "EXIT100": 1.00,
}
ADD_ACTIONS = {"ADD10": 0.10, "ADD20": 0.20, "ADD25": 0.25}
SIZE_ACTIONS = {"SIZE25": 0.25, "SIZE50": 0.50, "SIZE75": 0.75, "SIZE100": 1.00}
LONG_ACTIONS = {"LONG"}
SHORT_ACTIONS = {"SHORT"}
GATE_ACTIONS = {"BLOCK", "IGNORE", "WAIT"}


@dataclass(frozen=True)
class EngineConfig:
    entry_weight: float = 0.35  # per-rule confirmation weight of a LONG/SHORT rule
    plain_exit_fraction: float = 0.50  # weight of the generic "EXIT" action
    density_window: int = 5
    boost_step: float = 0.05


@dataclass
class EngineOutput:
    """Per-bar aggregation of every fired rule."""

    frame: pd.DataFrame
    fired: pd.DataFrame
    rules: list[Rule] = field(repr=False)

    def fired_names(self, i: int) -> list[str]:
        row = self.fired.iloc[i]
        return [name for name, hit in row.items() if hit]


class _LazyRow(Mapping):
    """Namespace exposing column ``i`` of pre-extracted numpy arrays."""

    def __init__(self, arrays: dict[str, np.ndarray], extra: dict[str, Any]):
        self._arrays = arrays
        self._extra = extra
        self.i = 0

    def __getitem__(self, key: str) -> Any:
        if key in self._extra:
            return self._extra[key]
        try:
            return self._arrays[key][self.i]
        except KeyError as exc:  # pragma: no cover - guarded by validation
            raise NameError(key) from exc

    def __iter__(self) -> Iterator[str]:
        return iter({**self._arrays, **self._extra})

    def __len__(self) -> int:
        return len(self._arrays) + len(self._extra)


class SignalEngine:
    def __init__(self, rules: list[Rule], cfg: EngineConfig | None = None):
        self.rules = rules
        self.cfg = cfg or EngineConfig()
        self.market_rules = [r for r in rules if r.phase == PHASE_MARKET]
        self.score_rules = [r for r in rules if r.phase == PHASE_SCORE]
        self.position_rules = [r for r in rules if r.phase == PHASE_POSITION]

    # ------------------------------------------------------------------ #
    # vectorised phases
    # ------------------------------------------------------------------ #
    def evaluate(self, features: pd.DataFrame) -> EngineOutput:
        namespace: dict[str, Any] = {c: features[c] for c in features.columns}
        market = self._run_vector(self.market_rules, namespace, features.index)

        scores = self._aggregate(market, self.market_rules, features.index)
        namespace.update({c: scores[c] for c in scores.columns})

        score_hits = self._run_vector(self.score_rules, namespace, features.index)
        fired = pd.concat([market, score_hits], axis=1)
        extra = self._aggregate(score_hits, self.score_rules, features.index)

        combined = scores.copy()
        combined["ExitFraction"] = scores["ExitFraction"].combine(
            extra["ExitFraction"], max
        )
        combined["SizeFraction"] = scores["SizeFraction"].combine(
            extra["SizeFraction"], max
        )
        combined["AddFraction"] = scores["AddFraction"].combine(extra["AddFraction"], max)
        combined["Blocked"] = scores["Blocked"] | extra["Blocked"]
        combined["BlockScore"] = scores["BlockScore"] + extra["BlockScore"]
        combined["BoostFactor"] = 1.0 + self.cfg.boost_step * _count(
            fired, self.rules, {"BOOST"}
        )
        combined["FinalEntryScore"] = (
            combined["EntryScore"] * combined["BoostFactor"]
        ).clip(0, 100)
        return EngineOutput(frame=combined, fired=fired, rules=self.rules)

    def _run_vector(
        self, rules: list[Rule], namespace: dict[str, Any], index: pd.Index
    ) -> pd.DataFrame:
        data: dict[str, np.ndarray] = {}
        for rule in rules:
            value = eval(rule.vector_code, {"__builtins__": {}}, namespace)  # noqa: S307
            series = (
                value
                if isinstance(value, pd.Series)
                else pd.Series(bool(value), index=index)
            )
            data[rule.name] = series.fillna(False).to_numpy(dtype=bool)
        return pd.DataFrame(data, index=index)

    def _aggregate(
        self, fired: pd.DataFrame, rules: list[Rule], index: pd.Index
    ) -> pd.DataFrame:
        cfg = self.cfg
        available = [r for r in rules if r.name in fired.columns]
        if not available:
            return _empty_aggregate(index)
        hits = fired[[r.name for r in available]].to_numpy(dtype=float)
        strength = np.array([r.strength for r in available])

        def weighted(mask: np.ndarray, scale: np.ndarray | None = None) -> np.ndarray:
            w = strength * (scale if scale is not None else 1.0)
            return hits @ (w * mask)

        is_long = np.array([r.action in LONG_ACTIONS for r in available], dtype=float)
        is_short = np.array([r.action in SHORT_ACTIONS for r in available], dtype=float)
        exit_frac = np.array(
            [
                EXIT_ACTIONS.get(r.action, cfg.plain_exit_fraction if r.action == "EXIT" else 0.0)
                for r in available
            ]
        )
        is_block = np.array([r.action == "BLOCK" for r in available], dtype=float)
        is_gate = np.array([r.action in GATE_ACTIONS for r in available], dtype=float)

        long_conf = _confluence(hits, strength / 100.0 * cfg.entry_weight * is_long)
        short_conf = _confluence(hits, strength / 100.0 * cfg.entry_weight * is_short)
        dominant = np.maximum(long_conf, short_conf)
        other = np.minimum(long_conf, short_conf)
        entry_score = np.clip(dominant - 0.5 * other, 0.0, 100.0)
        exit_score = _confluence(hits, strength / 100.0 * exit_frac)

        out = pd.DataFrame(index=index)
        out["LongWeight"] = long_conf
        out["ShortWeight"] = short_conf
        out["Direction"] = np.sign(long_conf - short_conf)
        out["EntryScore"] = entry_score
        out["ExitScore"] = exit_score
        out["BlockScore"] = weighted(is_block)
        out["Blocked"] = hits @ is_gate > 0
        out["LongCount"] = hits @ is_long
        out["ShortCount"] = hits @ is_short
        out["SignalCount"] = hits.sum(axis=1)
        out["SignalDensity"] = (
            out["SignalCount"].rolling(cfg.density_window, min_periods=1).sum()
        )
        out["ExitFraction"] = (hits * exit_frac).max(axis=1)
        out["SizeFraction"] = _max_action(hits, available, SIZE_ACTIONS)
        out["AddFraction"] = _max_action(hits, available, ADD_ACTIONS)
        out["ScalpSignal"] = _count(fired, available, {"SCALP"}) > 0
        out["EntryScoreFalling"] = out["EntryScore"].diff().fillna(0.0) < 0
        out["ExitScoreRising"] = out["ExitScore"].diff().fillna(0.0) > 0
        return out

    # ------------------------------------------------------------------ #
    # position phase
    # ------------------------------------------------------------------ #
    def position_namespace(self, features: pd.DataFrame, scores: pd.DataFrame) -> _LazyRow:
        arrays = {c: features[c].to_numpy() for c in features.columns}
        arrays.update({c: scores[c].to_numpy() for c in scores.columns})
        return _LazyRow(arrays, {"Profit": 0.0, "OppositeSignals": 0.0})

    def evaluate_position_rules(
        self, namespace: _LazyRow, i: int, profit: float, opposite: float
    ) -> list[Rule]:
        namespace.i = i
        namespace._extra["Profit"] = profit
        namespace._extra["OppositeSignals"] = opposite
        hits = []
        for rule in self.position_rules:
            if eval(rule.scalar_code, {"__builtins__": {}}, namespace):  # noqa: S307
                hits.append(rule)
        return hits


_AGGREGATE_COLUMNS = (
    "LongWeight",
    "ShortWeight",
    "Direction",
    "EntryScore",
    "ExitScore",
    "BlockScore",
    "LongCount",
    "ShortCount",
    "SignalCount",
    "SignalDensity",
    "ExitFraction",
    "SizeFraction",
    "AddFraction",
)


def _empty_aggregate(index: pd.Index) -> pd.DataFrame:
    out = pd.DataFrame(0.0, index=index, columns=list(_AGGREGATE_COLUMNS))
    for col in ("Blocked", "ScalpSignal", "EntryScoreFalling", "ExitScoreRising"):
        out[col] = False
    return out


def _confluence(hits: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Combine fired rules as independent confirmations, in percent.

    ``100 * (1 - prod(1 - w_j))`` over the rules that fired. A weight of 1
    (full confidence, full exit) saturates the score at exactly 100.
    """
    w = np.clip(weights, 0.0, 1.0)
    saturating = hits @ (w >= 1.0).astype(float) > 0
    logs = np.where(w >= 1.0, 0.0, np.log1p(-np.minimum(w, 0.999999)))
    combined = 100.0 * (1.0 - np.exp(hits @ logs))
    return np.where(saturating, 100.0, combined)


def _count(fired: pd.DataFrame, rules: list[Rule], actions: set[str]) -> np.ndarray:
    names = [r.name for r in rules if r.action in actions and r.name in fired.columns]
    if not names:
        return np.zeros(len(fired))
    return fired[names].to_numpy(dtype=float).sum(axis=1)


def _max_action(
    hits: np.ndarray, rules: list[Rule], mapping: dict[str, float]
) -> np.ndarray:
    weights = np.array([mapping.get(r.action, 0.0) for r in rules])
    return (hits * weights).max(axis=1)
