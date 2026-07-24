"""Live/paper-trading engine for the compression-breakout strategy.

Designed to run stateless once per hour (e.g. from GitHub Actions):

1. fetch the latest 1h candles (Binance public API has ``TakerBuyBase``, which
   the whale signal needs; CoinEx public API is the fallback, whale disabled);
2. update the open position with the causal staircase trailing stop, bar by
   bar, exactly as in the backtest;
3. evaluate the signal on the last *closed* bar and open a paper position at
   the current price if there is one;
4. persist everything to a small JSON/CSV state (committed back to the repo),
   and return the events so the caller can notify Telegram / render the
   dashboard.

No real order is ever sent from here. ``mode`` stays ``paper`` until
``paper_until`` has passed AND CoinEx API credentials are configured — the
first week is a mandatory dry run.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from .breakout import BreakoutConfig, _staircase_stop, build_breakout_signals

BINANCE_KLINES = (
    # the public market-data mirror is reachable from regions where
    # api.binance.com returns HTTP 451 (e.g. GitHub Actions US runners)
    "https://data-api.binance.vision/api/v3/klines?symbol={symbol}&interval=1h&limit={limit}"
)
COINEX_KLINES = (
    "https://api.coinex.com/v2/spot/kline?market={symbol}&period=1hour&limit={limit}"
)
STATE_VERSION = 1


def _http_json(url: str, timeout: int = 30):
    req = urllib.request.Request(url, headers={"User-Agent": "bank-signal/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def fetch_candles(symbol: str = "BTCUSDT", limit: int = 1000) -> pd.DataFrame:
    """Closed 1h candles, newest last. Binance first (has taker-buy volume),
    CoinEx as fallback (no taker data -> whale signal silently disabled)."""
    try:
        raw = _http_json(BINANCE_KLINES.format(symbol=symbol, limit=limit))
        df = pd.DataFrame(
            raw,
            columns=[
                "OpenTime", "Open", "High", "Low", "Close", "Volume",
                "CloseTime", "QuoteVolume", "Trades", "TakerBuyBase",
                "TakerBuyQuote", "_",
            ],
        )
        df["Time"] = pd.to_datetime(df["OpenTime"], unit="ms", utc=True)
        cols = ["Open", "High", "Low", "Close", "Volume", "TakerBuyBase"]
        df[cols] = df[cols].astype(float)
        df["Trades"] = df["Trades"].astype(int)
        df = df.set_index("Time")[[*cols, "Trades"]]
    except Exception:
        raw = _http_json(COINEX_KLINES.format(symbol=symbol, limit=min(limit, 1000)))
        rows = raw["data"]
        df = pd.DataFrame(rows)
        df["Time"] = pd.to_datetime(df["created_at"].astype(int), unit="ms", utc=True)
        for c in ("open", "high", "low", "close", "volume"):
            df[c.capitalize()] = df[c].astype(float)
        df = df.set_index("Time")[["Open", "High", "Low", "Close", "Volume"]]
        df["Trades"] = 0
    # drop the still-forming bar: its open time + 1h must be in the past
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    return df[df.index <= pd.Timestamp(cutoff)]


@dataclass
class LiveState:
    symbol: str = "BTCUSDT"
    mode: str = "paper"
    paper_until: str = ""  # ISO date; no real order before this
    equity: float = 1.0
    position: dict | None = None
    last_bar: str = ""
    trades: int = 0
    wins: int = 0
    updated_at: str = ""
    version: int = STATE_VERSION
    events: list = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> LiveState:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            data.pop("events", None)
            return cls(**data, events=[])
        state = cls()
        state.paper_until = (
            datetime.now(timezone.utc) + timedelta(days=7)
        ).strftime("%Y-%m-%d")
        return state

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {k: v for k, v in self.__dict__.items() if k != "events"}
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def step(
    state: LiveState,
    candles: pd.DataFrame,
    cfg: BreakoutConfig | None = None,
    trades_csv: Path | None = None,
) -> LiveState:
    """Process every new closed bar since ``state.last_bar``."""
    cfg = cfg or BreakoutConfig()
    d = build_breakout_signals(candles, cfg)
    new_bars = d[d.index > pd.Timestamp(state.last_bar)] if state.last_bar else d.tail(1)
    if new_bars.empty:
        return state

    for ts, row in new_bars.iterrows():
        _process_bar(state, ts, row, cfg, trades_csv)
    state.last_bar = str(new_bars.index[-1])
    state.updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return state


def _process_bar(state: LiveState, ts, row, cfg: BreakoutConfig, trades_csv) -> None:
    pos = state.position
    if pos is not None:
        pos["bars_held"] += 1
        exit_price, reason = _check_exit(pos, row, cfg)
        if exit_price is not None:
            _close_position(state, ts, exit_price, reason, cfg, trades_csv)
        else:
            # causal trailing update from this bar's extremes, for the NEXT bar
            fav = (
                (row["High"] - pos["entry_price"]) / pos["entry_price"]
                if pos["direction"] == "long"
                else (pos["entry_price"] - row["Low"]) / pos["entry_price"]
            )
            pos["best_fav"] = max(pos["best_fav"], float(fav))
            pos["stop"] = _staircase_stop(
                pos["stop"], pos["entry_price"], pos["best_fav"], pos["direction"], cfg
            )

    if state.position is None:
        direction = (
            "long" if row["long_signal"] else "short" if row["short_signal"] else None
        )
        if direction is None or (direction == "short" and not cfg.allow_short):
            return
        entry = float(row["Close"])  # live: enter at next tick ~ close of signal bar
        stop0 = float(row["roll_low"] if direction == "long" else row["roll_high"])
        risk = entry - stop0 if direction == "long" else stop0 - entry
        if risk <= 0:
            return
        target = entry + cfg.rr * risk if direction == "long" else entry - cfg.rr * risk
        state.position = {
            "direction": direction,
            "source": str(row["signal_source"]),
            "entry_time": str(ts),
            "entry_price": entry,
            "stop": stop0,
            "initial_stop": stop0,
            "target": target,
            "best_fav": 0.0,
            "bars_held": 0,
        }
        state.events.append(
            {
                "type": "entry",
                "time": str(ts),
                "direction": direction,
                "source": str(row["signal_source"]),
                "price": entry,
                "stop": stop0,
                "target": target,
            }
        )


def _check_exit(pos: dict, row, cfg: BreakoutConfig):
    hi, lo = float(row["High"]), float(row["Low"])
    if pos["direction"] == "long":
        if lo <= pos["stop"]:
            reason = "staircase-lock" if pos["stop"] != pos["initial_stop"] else "stop"
            return pos["stop"], reason
        if hi >= pos["target"]:
            return pos["target"], "target"
    else:
        if hi >= pos["stop"]:
            reason = "staircase-lock" if pos["stop"] != pos["initial_stop"] else "stop"
            return pos["stop"], reason
        if lo <= pos["target"]:
            return pos["target"], "target"
    if pos["bars_held"] >= cfg.hold_bars:
        return float(row["Close"]), "time-exit"
    return None, None


def _close_position(state, ts, exit_price, reason, cfg: BreakoutConfig, trades_csv):
    pos = state.position
    entry = pos["entry_price"]
    gross = (
        exit_price / entry - 1 if pos["direction"] == "long" else entry / exit_price - 1
    )
    ret = gross - cfg.round_trip_cost
    risk_pct = abs(entry - pos["initial_stop"]) / entry
    r_multiple = max(min(ret / risk_pct, cfg.r_multiple_cap), -1.5) if risk_pct else 0.0
    state.equity *= max(1 + cfg.risk_per_trade * r_multiple, 0.01)
    state.trades += 1
    state.wins += int(ret > 0)
    state.position = None
    record = {
        "entry_time": pos["entry_time"],
        "exit_time": str(ts),
        "direction": pos["direction"],
        "source": pos["source"],
        "entry_price": entry,
        "exit_price": float(exit_price),
        "exit_reason": reason,
        "ret_pct": ret,
        "r_multiple": r_multiple,
        "equity": state.equity,
    }
    state.events.append({"type": "exit", **record})
    if trades_csv is not None:
        trades_csv.parent.mkdir(parents=True, exist_ok=True)
        header = not trades_csv.exists()
        pd.DataFrame([record]).to_csv(trades_csv, mode="a", header=header, index=False)


def notify_telegram(token: str, chat_id: str, text: str) -> bool:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps(
        {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    ).encode()
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode()).get("ok", False)
    except Exception:
        return False


def format_event(event: dict, state: LiveState) -> str:
    mode = "PAPER" if state.mode == "paper" else "LIVE"
    if event["type"] == "entry":
        arrow = "🟢 LONG" if event["direction"] == "long" else "🔴 SHORT"
        return (
            f"<b>[{mode}] {arrow}</b> {state.symbol}\n"
            f"سیگنال: {event['source']}\n"
            f"ورود: {event['price']:,.1f}\n"
            f"استاپ: {event['stop']:,.1f} | هدف: {event['target']:,.1f}\n"
            f"⏱ {event['time']}"
        )
    pnl = event["ret_pct"] * 100
    icon = "✅" if pnl > 0 else "❌"
    return (
        f"<b>[{mode}] {icon} بسته شد</b> {state.symbol} {event['direction']}\n"
        f"خروج: {event['exit_price']:,.1f} ({event['exit_reason']})\n"
        f"بازده: {pnl:+.2f}% | R: {event['r_multiple']:+.2f}\n"
        f"موجودی: x{event['equity']:.4f} | معاملات: {state.trades} "
        f"(برد {state.wins})"
    )
