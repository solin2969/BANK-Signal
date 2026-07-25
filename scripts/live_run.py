"""Hourly live/paper-trading runner (GitHub Actions entry point).

    TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... python scripts/live_run.py

Fetches the latest candles, advances the paper-trading state, sends every
entry/exit (and a heartbeat once a day) to Telegram, and regenerates the
dashboard in ``docs/``.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from banksignal.breakout import BreakoutConfig  # noqa: E402
from banksignal.live import (  # noqa: E402
    LiveState,
    fetch_candles,
    format_event,
    notify_telegram,
    step,
)

STATE = Path("state/live_state.json")
TRADES = Path("state/paper_trades.csv")
DOCS = Path("docs")


def main() -> int:
    state = LiveState.load(STATE)
    candles = fetch_candles(state.symbol, limit=1000)
    if len(candles) < 400:
        print(f"not enough candles ({len(candles)}), aborting")
        return 1
    cfg = BreakoutConfig()
    state = step(state, candles, cfg, TRADES)
    state.save(STATE)

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    for event in state.events:
        text = format_event(event, state)
        print(text.replace("\n", " | "))
        if token and chat_id:
            notify_telegram(token, chat_id, text)
    if token and chat_id and _is_daily_heartbeat():
        notify_telegram(token, chat_id, _heartbeat_text(state, candles))

    _write_dashboard(state, candles)
    print(f"ok: last_bar={state.last_bar} equity=x{state.equity:.4f} "
          f"pos={'yes' if state.position else 'no'} events={len(state.events)}")
    return 0


def _is_daily_heartbeat() -> bool:
    return datetime.now(timezone.utc).hour == 20


def _heartbeat_text(state: LiveState, candles) -> str:
    price = candles["Close"].iloc[-1]
    win_rate = 100 * state.wins / state.trades if state.trades else 0.0
    pos = state.position
    pos_line = (
        f"پوزیشن باز: {pos['direction']} از {pos['entry_price']:,.1f} "
        f"(استاپ {pos['stop']:,.1f})"
        if pos
        else "پوزیشن باز: ندارد"
    )
    return (
        f"<b>📊 گزارش روزانه [{'PAPER' if state.mode == 'paper' else 'LIVE'}]</b>\n"
        f"{state.symbol}: {price:,.1f}\n"
        f"موجودی: x{state.equity:.4f}\n"
        f"معاملات: {state.trades} | نرخ برد: {win_rate:.1f}%\n"
        f"{pos_line}\n"
        f"حالت واقعی از: {state.paper_until}"
    )


def _write_dashboard(state: LiveState, candles) -> None:
    DOCS.mkdir(exist_ok=True)
    trades = []
    if TRADES.exists():
        import pandas as pd

        trades = json.loads(
            pd.read_csv(TRADES).tail(200).to_json(orient="records")
        )
    status = {
        "symbol": state.symbol,
        "mode": state.mode,
        "paper_until": state.paper_until,
        "equity": state.equity,
        "trades": state.trades,
        "wins": state.wins,
        "position": state.position,
        "last_bar": state.last_bar,
        "updated_at": state.updated_at,
        "price": float(candles["Close"].iloc[-1]),
        "recent_trades": trades,
    }
    (DOCS / "status.json").write_text(
        json.dumps(status, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    raise SystemExit(main())
