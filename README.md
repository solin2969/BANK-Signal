# BANK-Signal

A complete trading system whose **only** source of truth is `rules/bank.csv`.

`bank.csv` is a list of 159 `if <condition>: add_signal(i, "<NAME>", "<ACTION>", w, w, w)`
blocks. This repository parses that file as-is, computes every variable it
references from raw OHLCV candles, evaluates the rules bar by bar, executes the
resulting actions in a backtester, and reports the performance. Editing
`bank.csv` changes the traded system - no Python change is required.

```
rules/bank.csv ──► rules.py (parser)      ──┐
                                            ├─► engine.py (signals + scores) ──► backtest.py ──► metrics.py / report.py
data/*.parquet ──► data.py ──► features.py ─┘
```

## Quick start

```bash
pip install -r requirements.txt

python -m banksignal.cli rules                      # what the rule file contains
python -m banksignal.cli backtest --no-short        # full backtest + report
python -m banksignal.cli signals --tail 20          # signals of the latest bars
python scripts/edge_analysis.py                     # is there any edge at all?
python scripts/diagnostics.py                       # why trades fail + build rules/bank_filtered.csv
python scripts/optimize.py --train-end 2021-12-31   # grid search execution params
python scripts/validate.py                          # out-of-sample check of the choices above
```

Reports are written to `reports/`: `backtest_report.md`, `equity_curve.png`,
`trades.csv`, `edge_analysis.md`.

## How the rule file is executed

| phase | rules | when | how |
| --- | ---: | --- | --- |
| `market` | 112 | conditions on market variables only | vectorised over the whole frame |
| `score` | 33 | conditions on `EntryScore`/`ExitScore`/`BlockScore`/`SignalCount`/`SignalDensity` | vectorised, after the scores of phase 1 |
| `position` | 14 | conditions on `Profit`/`OppositeSignals` | per bar, inside the backtest loop |

Boolean operators are rewritten to their elementwise equivalents
(`and` -> `&`) by an AST transformer, so the original text of each condition is
evaluated - never a hand-written copy of it.

Scores are computed **from phase 1 only**, otherwise rules such as `EXIT_Q1`
(which fires *because* `ExitScore` is high) would inflate the very score that
triggered them. Rules combine as independent confirmations rather than as a
sum:

```
score = 100 * (1 - Π (1 - weight_of_fired_rule))
EntryScore : weight = 0.35 * strength/100     (dominant side minus half of the opposite side)
ExitScore  : weight = exit_fraction * strength/100   (100 only for a full exit at full confidence)
BlockScore : sum of the strengths of fired BLOCK rules
```

### Actions

| action | effect |
| --- | --- |
| `LONG` / `SHORT` | directional vote, feeds `EntryScore` and the traded direction |
| `EXIT`, `EXIT10`..`EXIT100` | close that percentage of the position (`EXIT` = 50%) |
| `ADD10/20/25` | pyramid into the winner |
| `SIZE25/50/75/100` | position size of the next entry |
| `BOOST` | multiplies `EntryScore` by `1 + 0.05 * n_boosts` |
| `BLOCK`, `IGNORE`, `WAIT` | no new entries on that bar |
| `AUTO`, `AUTO`-like informational | counted in `SignalCount` only |
| `SCALP` | flagged in the signal frame (`ScalpSignal`) |

### Execution model

* signals come from the close of bar `i` and are filled at the **open of bar
  `i+1`** - no look-ahead;
* the ATR stop is the only intrabar fill and is assumed to fill first;
* taker fee 0.04% + 0.02% slippage on every fill;
* one position at a time, sized as a fraction of equity, `min_hold_bars`
  prevents same-bar churn.

## Feature engine

`features.py` derives every identifier used by `bank.csv` from OHLCV plus
`TakerBuyBase` (real order-flow delta from Binance klines):

* **order flow**: `Delta` (buy-sell volume normalised by average volume),
  `Pressure`, their slopes/recovery flags;
* **energy**: `Energy = range/ATR * volume/avg_volume`, its average, slope,
  acceleration, 50/100-bar maxima, collapse and recovery flags;
* **structure**: fractal swings (confirmed 5 bars later, so they are causal),
  `HigherHigh/LowerLow/...`, `MarketStructure`, break of structure with retest
  and failure, `SwingBroken*`;
* **fibonacci**: 0.236/0.382/0.5/0.618/0.786 of the last completed leg with an
  ATR tolerance, plus `FiboFailure`;
* **waves**: position inside the running leg (measured against the previous
  leg), strength, acceleration, failure;
* **levels/barriers**: 200 and 1000-bar extremes, touch-counted
  support/resistance strength, barrier score ahead of price;
* **whales**: volume spikes with directional pressure, `WhaleStillInside`,
  `OppositeWhale`, `WhaleExit`;
* **liquidity**: grabs, absorption, vacuum, traps;
* **regime**: trend direction/strength/score, momentum cycle, compression,
  noise, `DataQualityLow`, and the candle `DNA` classification.

Feature thresholds live in `FeatureConfig`, engine weights in `EngineConfig`,
execution parameters in `BacktestConfig` - none of the rule semantics are
hard-coded in the code.

## Results on BTCUSDT 1h (2020-01-01 -> 2026-01-24, 53 147 bars)

Best long-only configuration found in-sample (2020-2021), then applied
unchanged out-of-sample:

| window | return | buy & hold | max DD | Sharpe | trades | win rate | profit factor |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| in-sample 2020-2021 | **+30.4%** | +544% | -18.4% | 0.70 | 818 | 45% | 1.16 |
| out-of-sample 2022-2026 | **-34.9%** | +92% | -36.9% | -0.65 | 1 650 | 43% | 0.93 |
| full period | **-16.0%** | +1 146% | -48.3% | -0.07 | 2 473 | 45% | 1.03 |

`scripts/edge_analysis.py` explains why: measured against the unconditional
forward return, the directional signals carry almost no information at this
timeframe.

* baseline 6h forward return: +0.041%; the best individual rule adds +0.05pp,
  most add less than +0.01pp - all far below the ~0.12% round-trip cost;
* `EntryScore > 80` bars are **not** better than `EntryScore < 40` bars;
* `SHORT` signals are followed by *positive* returns on average (the sample is
  dominated by a bull market).

In other words, the ruleset as written is an exit-heavy trend-following
overlay whose entries do not beat holding BTC on 1h candles. The honest
conclusion is that it needs different features/timeframes, not different
execution parameters - tuning the execution grid (576 combinations) never
produced an out-of-sample edge.

## Quality filtering: `rules/bank_filtered.csv`

`scripts/diagnostics.py` measures every directional rule on the training window
only (2020-2021) and keeps a rule when it has, on at least two of the horizons
6h/24h/72h, an edge of >= 0.02pp over the unconditional forward return with
`t >= 1.5`, at least 100 signals and a firing rate <= 35%. It writes
`reports/rule_quality.csv` (every rule with its edge, t-stat and rejection
reason) and copies the surviving blocks verbatim into `rules/bank_filtered.csv`,
which the same parser executes.

**11 of 105 directional rules survived** - the rejected ones:

| reason | rules |
| --- | ---: |
| no consistent edge | 62 |
| too few signals (<100) | 21 |
| fires on more than 35% of bars | 11 |

The survivors are three long entries (`SUPPORT_MAJOR`, `SWING_REVERSAL_BUY`,
`EARLY_WAVE_LONG`) and eight exits (`MASTER_FORCE_EXIT`, `MASTER_EXIT_ALL`,
`FORCE_CLOSE`, `EMERGENCY_EXIT_04`, `STRUCTURE_FAILURE_LONG/SHORT`,
`DELTA_EXHAUSTION`, `PRESSURE_EXHAUSTION`). **No short rule survived.**

**9 of the 11 keep a positive 24h edge out-of-sample** (2022-2026), so the
selection is not pure curve fitting - but the edge shrinks by roughly a half to
a third (e.g. `MASTER_FORCE_EXIT` 0.19pp -> 0.07pp), which is the same order of
magnitude as the 0.12pp round-trip cost.

Backtest with the filtered file (`--rules rules/bank_filtered.csv`, long only,
same execution parameters as above):

| window | filtered | all rules |
| --- | ---: | ---: |
| full period return | **-3.5%** | -16.0% |
| out-of-sample return | **+13.1%** | -34.9% |
| max drawdown | -30.4% | -48.3% |
| trades | 613 | 2 473 |
| profit factor | 1.03 | 1.03 |

Filtering removes most of the damage but does not create a profitable system:
`reports/validation.md` shows that re-tuning the execution parameters on the
filtered rules gives +45% in-sample and -13% out-of-sample, and that **none of
the 20 best in-sample parameter sets is positive out-of-sample** - the
remaining edge is smaller than the trading costs plus the parameter noise.

### Why the trades fail (`reports/diagnostics.md`)

* the exit engine dominates: most positions are closed by `SIGNAL_EXIT`
  long before the 24-72h horizon at which the surviving rules actually have
  their edge;
* average MFE +0.6% against average MAE -0.4% with only 20% of trades ever more
  than 1% in profit - winners are cut early, so the win rate near 44% cannot
  pay the costs;
* losses concentrate in `RANGE` structure and low-volatility buckets, where the
  entry rules keep firing;
* the worst entry rules in real trades (`FIB_236_LONG`, `MARUBOZU_BULL`,
  `SWING_REVERSAL_BUY` in the unfiltered set) are exactly those the edge test
  rejects.

### Where to iterate

1. Replace the interpretations of the weakest variables in `features.py` (they
   are documented above and each one is a small function).
2. Re-run `scripts/edge_analysis.py`: only keep rules with a positive edge over
   several horizons.
3. Then re-run `scripts/optimize.py` and finally the full backtest.

## The strategy that works: compression breakout (`banksignal/breakout.py`)

A separate, self-contained strategy distilled from the whole research path -
it does not use `bank.csv` but implements what the failure analysis pointed
at: trade only clean structure breaks out of genuinely compressed ranges, and
never hand a winner back.

* entry: close breaks the 20-bar range by >0.1%, with a decisive body
  (>=55%), a small opposing wick (<=25%), volume >=1.2x average, the range in
  the tighter half of its own 250-bar history, not on Saturday or in the dead
  hours 19-21/00 UTC, and not against the strongest 10% of opposing 4h trends;
* exit: staircase trailing stop that locks 90/93/96/97% of the favourable
  excursion at +0.7/1.5/3/5%, target at 2x risk, time exit after 10 bars;
* costs: 0.05% fee + 0.02% slippage per side.

The trailing stop is **causal**: the stop active during a bar was fixed at the
end of the previous bar, so a bar's own high cannot lock a profit that the
same bar's low then collects (that optimism is worth ~240pp of total return
and is disabled by default; `--optimistic` reproduces it).

Parameters calibrated on 2020-2023 only; 2024-2026 untouched:

| window | return | win rate | PF | max DD | trades |
| --- | ---: | ---: | ---: | ---: | ---: |
| train 2020-2023 | +559% | 71.6% | 1.94 | -12.8% | 479 |
| **test 2024-2026** | **+42%** | 64.4% | 1.30 | -20.5% | 264 |
| full period | +839% | 69.0% | 1.69 | -20.5% | 743 |

```bash
python scripts/breakout_backtest.py --train-end 2024-01-01   # reports/breakout/
```

Caveats: ~15 hand-picked parameters were still chosen with knowledge of
2020-2023, the day/hour filters are the most fragile part, and per-trade
compounding assumes full-equity allocation on every trade. Forward-test with
small size before believing the compounded figure.

## Tests

```bash
python -m pytest -q     # rule parsing, causality of features, backtest invariants, breakout strategy
ruff check .
```

The causality test truncates the input data and asserts that earlier features
do not change - the usual source of accidental look-ahead in this kind of
system.

---

## خلاصه فارسی

* `rules/bank.csv` تنها مرجع سیستم است؛ کد آن را همان‌طور که هست پارس و اجرا
  می‌کند (۱۵۹ قانون، در سه فاز: بازار، امتیازها، وابسته به پوزیشن).
* تمام متغیرهای داخل فایل (Delta، Energy، Whale، Fibo، BOS، Wave، ساختار،
  نقدینگی، DNA و …) در `features.py` از روی کندل‌های خام محاسبه می‌شوند.
* بک‌تست روی BTCUSDT یک‌ساعته از ۲۰۲۰ تا ۲۰۲۶ اجرا شده است. نتیجه صادقانه:
  در دوره‌ی تنظیم (۲۰۲۰-۲۰۲۱) سود +۳۰٪، اما خارج از نمونه (۲۰۲۲ به بعد)
  −۳۵٪ - یعنی سیگنال‌ها در این تایم‌فریم برتری واقعی ندارند.
* تحلیل `scripts/edge_analysis.py` نشان می‌دهد بازده آینده بعد از سیگنال‌ها
  تقریباً برابر بازده پایه است؛ بنابراین قبل از معامله‌ی واقعی باید تعریف
  متغیرها یا تایم‌فریم تغییر کند.
* `scripts/diagnostics.py` علت خطاها را استخراج می‌کند و فقط قوانین باکیفیت را
  در `rules/bank_filtered.csv` نگه می‌دارد: از ۱۰۵ قانون جهت‌دار فقط ۱۱ تا
  (۳ ورود لانگ و ۸ خروج) از فیلتر عبور کردند و ۹ تای آن‌ها خارج از نمونه هم
  edge مثبت دارند. با این فایل، ضرر کل دوره از −۱۶٪ به −۳.۵٪ و ضرر خارج از
  نمونه به +۱۳٪ تغییر می‌کند، اما هنوز سیستم سودده پایدار نیست.
* `banksignal/breakout.py` استراتژی «شکست فشردگی + قفل پلکانی سود» است که
  از کل مسیر تحقیق بیرون آمد و مستقل تأیید شد: کل دوره +۸۳۹٪، خارج از نمونه
  (۲۰۲۴-۲۰۲۶) +۴۲٪ با نرخ برد ۶۹٪ — با تریلینگ استاپ کاملاً علّی (بدون
  خوش‌بینی درون‌کندلی). قبل از پول واقعی حتماً Forward Test شود.
