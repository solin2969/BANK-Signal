"""Event-driven backtester for the bank.csv signal system.

Execution model
---------------
* signals are produced from the *close* of bar ``i`` and filled at the *open*
  of bar ``i+1`` (no look-ahead);
* protective stops are the only intrabar fills; when a bar could have hit both
  the stop and a signal exit, the stop is assumed to fill first;
* fees and slippage are charged on every fill, on notional;
* one position at a time, sized as a fraction of current equity, scaled in via
  ``ADD*`` rules and scaled out via ``EXIT*`` rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .engine import ADD_ACTIONS, EXIT_ACTIONS, EngineOutput, SignalEngine


@dataclass(frozen=True)
class BacktestConfig:
    initial_equity: float = 10_000.0
    base_size: float = 0.25  # fraction of equity when no SIZE* rule fires
    max_size: float = 1.00
    entry_threshold: float = 60.0  # minimum FinalEntryScore to open a position
    exit_threshold: float = 0.0  # ignore signal exits below this ExitScore
    exit_score_force: float = 100.0  # ExitScore that closes the whole position
    stop_atr_mult: float = 2.0
    trail_atr_mult: float = 0.0  # 0 disables the ATR trailing stop
    fee_rate: float = 0.0004  # taker fee per fill
    slippage_rate: float = 0.0002
    allow_short: bool = True
    allow_reversal: bool = True
    min_hold_bars: int = 1


@dataclass
class Trade:
    entry_time: pd.Timestamp
    direction: int
    entry_price: float
    qty: float
    initial_qty: float = 0.0
    exit_time: pd.Timestamp | None = None
    exit_price: float | None = None
    pnl: float = 0.0
    fees: float = 0.0
    bars: int = 0
    mfe: float = 0.0
    mae: float = 0.0
    entry_score: float = 0.0
    entry_reasons: list[str] = field(default_factory=list)
    exit_reasons: list[str] = field(default_factory=list)

    @property
    def is_open(self) -> bool:
        return self.exit_time is None

    @property
    def return_pct(self) -> float:
        """PnL as a percentage of the notional that was put at risk."""
        notional = self.entry_price * (self.initial_qty or self.qty)
        return 100.0 * self.pnl / notional if notional else 0.0


@dataclass
class BacktestResult:
    equity: pd.Series
    trades: pd.DataFrame
    signals: pd.DataFrame
    config: BacktestConfig


class Backtester:
    def __init__(self, engine: SignalEngine, cfg: BacktestConfig | None = None):
        self.engine = engine
        self.cfg = cfg or BacktestConfig()

    def run(self, features: pd.DataFrame, output: EngineOutput) -> BacktestResult:  # noqa: C901
        cfg = self.cfg
        scores = output.frame
        idx = features.index
        n = len(idx)

        open_ = features["Open"].to_numpy()
        high = features["High"].to_numpy()
        low = features["Low"].to_numpy()
        close = features["Close"].to_numpy()
        atr = features["ATR"].to_numpy()

        direction_v = scores["Direction"].to_numpy()
        entry_score_v = scores["FinalEntryScore"].to_numpy()
        exit_score_v = scores["ExitScore"].to_numpy()
        exit_frac_v = scores["ExitFraction"].to_numpy()
        size_frac_v = scores["SizeFraction"].to_numpy()
        add_frac_v = scores["AddFraction"].to_numpy()
        blocked_v = scores["Blocked"].to_numpy()
        block_score_v = scores["BlockScore"].to_numpy()
        long_count_v = scores["LongCount"].to_numpy()
        short_count_v = scores["ShortCount"].to_numpy()

        pos_ns = self.engine.position_namespace(features, scores)

        cash = cfg.initial_equity
        equity_curve = np.empty(n)
        trades: list[Trade] = []
        pos: Trade | None = None
        stop_price = np.nan
        pending: dict | None = None

        for i in range(n):
            price_open = open_[i]

            # 1. fill orders queued on the previous bar ----------------------
            if pending is not None:
                cash, pos, stop_price = self._execute(
                    pending, price_open, atr[i], idx[i], cash, pos, stop_price, trades
                )
                pending = None

            # 2. protective stop, intrabar ------------------------------------
            if pos is not None and not np.isnan(stop_price):
                hit = (
                    low[i] <= stop_price if pos.direction > 0 else high[i] >= stop_price
                )
                if hit:
                    cash += self._close(pos, stop_price, 1.0, idx[i], "STOP_LOSS")
                    trades.append(pos)
                    pos, stop_price = None, np.nan

            # 3. track excursions ---------------------------------------------
            if pos is not None:
                pos.bars += 1
                move = (close[i] - pos.entry_price) / pos.entry_price * pos.direction
                pos.mfe = max(pos.mfe, 100.0 * move)
                pos.mae = min(pos.mae, 100.0 * move)
                if cfg.trail_atr_mult > 0 and atr[i] > 0:
                    trail = close[i] - pos.direction * cfg.trail_atr_mult * atr[i]
                    stop_price = (
                        max(stop_price, trail) if pos.direction > 0 else min(stop_price, trail)
                    )

            # 4. build the order for the next bar ------------------------------
            profit = 0.0
            opposite = 0.0
            exit_fraction = (
                float(exit_frac_v[i]) if exit_score_v[i] >= cfg.exit_threshold else 0.0
            )
            force_exit = exit_score_v[i] >= cfg.exit_score_force
            add_fraction = float(add_frac_v[i])
            reasons: list[str] = []

            if pos is not None:
                profit = (
                    100.0 * (close[i] - pos.entry_price) / pos.entry_price * pos.direction
                )
                opposite = (
                    short_count_v[i] if pos.direction > 0 else long_count_v[i]
                )
                for rule in self.engine.evaluate_position_rules(
                    pos_ns, i, profit, float(opposite)
                ):
                    reasons.append(rule.name)
                    if rule.action in EXIT_ACTIONS:
                        exit_fraction = max(exit_fraction, EXIT_ACTIONS[rule.action])
                    elif rule.action == "EXIT":
                        exit_fraction = max(
                            exit_fraction, self.engine.cfg.plain_exit_fraction
                        )
                    elif rule.action in ADD_ACTIONS:
                        add_fraction = max(add_fraction, ADD_ACTIONS[rule.action])

            if force_exit:
                exit_fraction = 1.0

            wants_long = direction_v[i] > 0 and entry_score_v[i] >= cfg.entry_threshold
            wants_short = (
                cfg.allow_short
                and direction_v[i] < 0
                and entry_score_v[i] >= cfg.entry_threshold
            )
            gated = bool(blocked_v[i]) or block_score_v[i] > 0

            if pos is not None:
                desired_dir = 1 if wants_long else (-1 if wants_short else 0)
                if (
                    cfg.allow_reversal
                    and desired_dir != 0
                    and desired_dir != pos.direction
                    and not gated
                    and pos.bars >= cfg.min_hold_bars
                ):
                    pending = {
                        "type": "reverse",
                        "direction": desired_dir,
                        "size": self._size(size_frac_v[i]),
                        "score": entry_score_v[i],
                        "reasons": output.fired_names(i)[:8],
                    }
                elif exit_fraction > 0 and pos.bars >= cfg.min_hold_bars:
                    pending = {
                        "type": "exit",
                        "fraction": min(1.0, exit_fraction),
                        "reasons": reasons or ["SIGNAL_EXIT"],
                    }
                elif add_fraction > 0:
                    pending = {"type": "add", "fraction": add_fraction, "reasons": reasons}
            elif (wants_long or wants_short) and not gated:
                pending = {
                    "type": "entry",
                    "direction": 1 if wants_long else -1,
                    "size": self._size(size_frac_v[i]),
                    "score": entry_score_v[i],
                    "reasons": output.fired_names(i)[:8],
                }

            unrealised = (
                (close[i] - pos.entry_price) * pos.qty * pos.direction if pos else 0.0
            )
            equity_curve[i] = cash + unrealised

        if pos is not None:
            cash += self._close(pos, close[-1], 1.0, idx[-1], "END_OF_DATA")
            trades.append(pos)
            equity_curve[-1] = cash

        return BacktestResult(
            equity=pd.Series(equity_curve, index=idx, name="equity"),
            trades=_trades_frame(trades),
            signals=scores,
            config=cfg,
        )

    # ------------------------------------------------------------------ #
    def _size(self, size_fraction: float) -> float:
        cfg = self.cfg
        size = size_fraction if size_fraction > 0 else cfg.base_size
        return float(min(size, cfg.max_size))

    def _execute(
        self,
        order: dict,
        price: float,
        atr: float,
        when: pd.Timestamp,
        cash: float,
        pos: Trade | None,
        stop_price: float,
        trades: list[Trade],
    ) -> tuple[float, Trade | None, float]:
        cfg = self.cfg
        kind = order["type"]

        if kind in {"exit", "reverse"} and pos is not None:
            fraction = 1.0 if kind == "reverse" else order["fraction"]
            cash += self._close(pos, price, fraction, when, ", ".join(order["reasons"]))
            if pos.qty <= 1e-12:
                trades.append(pos)
                pos, stop_price = None, np.nan
            if kind == "reverse":
                pos, stop_price = None, np.nan

        if kind in {"entry", "reverse"} and pos is None:
            direction = order["direction"]
            fill = price * (1 + direction * cfg.slippage_rate)
            notional = cash * order["size"]
            qty = notional / fill if fill > 0 else 0.0
            fee = notional * cfg.fee_rate
            cash -= fee
            if qty > 0:
                pos = Trade(
                    entry_time=when,
                    direction=direction,
                    entry_price=fill,
                    qty=qty,
                    initial_qty=qty,
                    fees=fee,
                    entry_score=order.get("score", 0.0),
                    entry_reasons=list(order.get("reasons", [])),
                )
                stop_price = (
                    fill - direction * cfg.stop_atr_mult * atr
                    if atr > 0
                    else np.nan
                )

        if kind == "add" and pos is not None:
            direction = pos.direction
            fill = price * (1 + direction * cfg.slippage_rate)
            notional = cash * order["fraction"]
            qty = notional / fill if fill > 0 else 0.0
            if qty > 0:
                fee = notional * cfg.fee_rate
                cash -= fee
                pos.fees += fee
                total = pos.qty + qty
                pos.entry_price = (pos.entry_price * pos.qty + fill * qty) / total
                pos.qty = total
                pos.initial_qty += qty
                pos.entry_reasons.extend(order["reasons"])

        return cash, pos, stop_price

    def _close(
        self,
        pos: Trade,
        price: float,
        fraction: float,
        when: pd.Timestamp,
        reason: str,
    ) -> float:
        cfg = self.cfg
        qty = pos.qty * fraction
        fill = price * (1 - pos.direction * cfg.slippage_rate)
        gross = (fill - pos.entry_price) * qty * pos.direction
        fee = fill * qty * cfg.fee_rate
        pos.qty -= qty
        pos.pnl += gross - fee
        pos.fees += fee
        pos.exit_reasons.append(reason)
        if pos.qty <= 1e-12:
            pos.qty = 0.0
            pos.exit_time = when
            pos.exit_price = fill
        return gross - fee


def _trades_frame(trades: list[Trade]) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame(
            columns=[
                "entry_time",
                "exit_time",
                "direction",
                "entry_price",
                "exit_price",
                "pnl",
                "return_pct",
                "bars",
                "mfe",
                "mae",
                "entry_score",
                "entry_reasons",
                "exit_reasons",
            ]
        )
    return pd.DataFrame(
        [
            {
                "entry_time": t.entry_time,
                "exit_time": t.exit_time,
                "direction": "LONG" if t.direction > 0 else "SHORT",
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "pnl": t.pnl,
                "return_pct": t.return_pct,
                "bars": t.bars,
                "mfe": t.mfe,
                "mae": t.mae,
                "entry_score": t.entry_score,
                "entry_reasons": ",".join(dict.fromkeys(t.entry_reasons)),
                "exit_reasons": ",".join(dict.fromkeys(t.exit_reasons)),
            }
            for t in trades
        ]
    )
