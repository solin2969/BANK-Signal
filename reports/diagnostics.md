# Diagnostics

Training window `2020-01-01 00:00:00` -> `2021-12-31 00:00:00` (17490 bars). Every number below is measured on this window only; the filtered rule file it produces is validated on later data.

## 1. Why the trades fail

Baseline: 818 trades, win rate 47.2%, expectancy -0.256% per trade, profit factor 1.16.

### Losses by exit reason

| primary_exit | trades | win_rate | avg_return | total_pnl | avg_bars | avg_mfe | avg_mae |
| --- | --- | --- | --- | --- | --- | --- | --- |
| STOP_LOSS | 195 | 0.000 | -2.808 | -20151.578 | 5.503 | 0.310 | -1.359 |
| SIGNAL_EXIT | 366 | 0.423 | -0.235 | -3261.563 | 15.320 | 1.310 | -1.178 |
| DEFENSE_03 | 45 | 0.489 | -0.021 | -5.784 | 15.778 | 1.120 | -0.990 |
| PYRAMID_LEVEL2 | 6 | 1.000 | 2.439 | 713.003 | 13.167 | 3.309 | -0.445 |
| SCALE_OUT_10 | 43 | 0.977 | 0.662 | 1635.082 | 14.581 | 1.824 | -0.525 |
| SCALE_OUT_30 | 13 | 1.000 | 2.614 | 2448.989 | 12.769 | 3.443 | -0.258 |
| TRAIL_WAVE | 7 | 1.000 | 5.350 | 2775.420 | 12.286 | 5.641 | -0.114 |
| TRAIL_DELTA | 15 | 1.000 | 3.311 | 4179.147 | 14.400 | 4.151 | -0.373 |
| TRAIL_ENERGY | 128 | 0.984 | 2.036 | 16184.971 | 13.805 | 3.251 | -0.496 |

### Result by market context at entry

| regime | trades | win_rate | avg_return | total_pnl |
| --- | --- | --- | --- | --- |
| BEAR | 226 | 0.562 | 0.004 | 5706.366 |
| BULL | 592 | 0.438 | -0.355 | -1188.678 |

| trend | trades | win_rate | avg_return | total_pnl |
| --- | --- | --- | --- | --- |
| strong | 575 | 0.485 | -0.274 | 5650.570 |
| weak | 243 | 0.440 | -0.213 | -1132.882 |

| volatility | trades | win_rate | avg_return | total_pnl |
| --- | --- | --- | --- | --- |
| low | 273 | 0.495 | -0.073 | -3.917 |
| mid | 272 | 0.434 | -0.244 | 1321.147 |
| high | 273 | 0.487 | -0.451 | 3200.458 |

### Entry rules present in losing trades

| rule | trades | win_rate | avg_return | total_pnl |
| --- | --- | --- | --- | --- |
| MARUBOZU_BULL | 66 | 0.348 | -0.836 | -891.213 |
| TREND_RESUME_01 | 45 | 0.356 | -0.815 | -792.495 |
| FIB_236_SHORT | 44 | 0.341 | -0.750 | -56.938 |
| BOS_CONTINUE_SHORT | 40 | 0.400 | -0.655 | -945.194 |
| ANTI_LATE_WAVE | 145 | 0.421 | -0.611 | -1897.907 |
| MARUBOZU_BEAR | 46 | 0.326 | -0.603 | 241.680 |
| ANTI_FIBO | 96 | 0.448 | -0.569 | -847.231 |
| RESISTANCE_MAJOR | 50 | 0.460 | -0.544 | -72.191 |
| STRONG_WAVE | 198 | 0.455 | -0.522 | -2271.801 |
| HIGHER_LOW | 68 | 0.397 | -0.479 | -811.356 |
| ENERGY_RECOVER | 318 | 0.431 | -0.450 | -1619.785 |
| LATE_WAVE_EXIT | 179 | 0.458 | -0.438 | -1388.763 |
| CONFLUENCE_03 | 74 | 0.405 | -0.434 | -704.699 |
| CASCADE_03 | 53 | 0.396 | -0.397 | -504.171 |
| TREND_Q4 | 199 | 0.482 | -0.379 | 262.334 |
| BULL_STRUCTURE | 294 | 0.435 | -0.334 | -450.549 |
| CONFLUENCE_02 | 112 | 0.420 | -0.324 | -260.053 |
| DNA_ACCUMULATION_01 | 85 | 0.506 | -0.324 | 198.989 |
| FIB_382_LONG | 78 | 0.449 | -0.310 | 1092.989 |
| TRIPLE_CONFIRMATION | 142 | 0.401 | -0.306 | 137.249 |

### Cost of churn

* trades: 818, average holding time: 12.6 bars

* average MFE +1.53% vs average MAE -1.03% - 51% of trades were more than 1% in profit at some point

## 2. Rule quality

Kept **11** of 105 directional rules (min 100 signals, max 35% firing rate, edge >= 0.02pp with t >= 1.5 on at least 2 of the horizons (6, 24, 72)).

### Rejection reasons

| reason | rules |
| --- | --- |
| no consistent edge | 62 |
| too few signals | 21 |
| kept | 11 |
| fires too often | 11 |

### Kept rules

| rule | action | signals | frequency | edge_6h | edge_24h | edge_72h | t_6h | t_24h | t_72h | reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SWING_REVERSAL_BUY | LONG | 760 | 0.043 | 0.109 | 0.346 | 0.773 | 1.508 | 2.258 | 3.188 | kept |
| SUPPORT_MAJOR | LONG | 1358 | 0.078 | 0.122 | 0.325 | 0.622 | 1.394 | 2.056 | 2.641 | kept |
| STRUCTURE_FAILURE_SHORT | EXIT100 | 1169 | 0.067 | -0.065 | 0.183 | 0.678 | -1.273 | 1.582 | 3.933 | kept |
| PRESSURE_EXHAUSTION | EXIT50 | 1561 | 0.089 | 0.061 | 0.176 | 0.411 | 1.286 | 1.725 | 2.438 | kept |
| EMERGENCY_EXIT_04 | EXIT100 | 2284 | 0.131 | 0.012 | 0.251 | 0.362 | 0.320 | 2.981 | 2.823 | kept |
| DELTA_EXHAUSTION | EXIT50 | 1624 | 0.093 | 0.054 | 0.179 | 0.371 | 1.153 | 1.791 | 2.262 | kept |
| MASTER_FORCE_EXIT | EXIT100 | 3446 | 0.197 | 0.009 | 0.191 | 0.331 | 0.281 | 2.687 | 3.034 | kept |
| MASTER_EXIT_ALL | EXIT100 | 3446 | 0.197 | 0.009 | 0.191 | 0.331 | 0.281 | 2.687 | 3.034 | kept |
| FORCE_CLOSE | EXIT100 | 3446 | 0.197 | 0.009 | 0.191 | 0.331 | 0.281 | 2.687 | 3.034 | kept |
| EARLY_WAVE_LONG | LONG | 1881 | 0.108 | 0.034 | 0.197 | 0.251 | 0.674 | 2.170 | 1.737 | kept |
| STRUCTURE_FAILURE_LONG | EXIT100 | 1115 | 0.064 | 0.093 | 0.322 | 0.026 | 1.667 | 2.629 | 0.138 | kept |

### Worst 15 rejected rules

| rule | action | signals | frequency | edge_6h | edge_24h | edge_72h | t_6h | t_24h | t_72h | reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| HIST1000_BUY | LONG | 30 | 0.002 | -1.074 | -4.210 | -6.796 | -0.847 | -1.867 | -2.710 | too few signals |
| MAJOR_DEMAND | LONG | 30 | 0.002 | -1.074 | -4.210 | -6.796 | -0.847 | -1.867 | -2.710 | too few signals |
| TREND_RESUME_05 | SHORT | 58 | 0.003 | -1.142 | -2.003 | -1.315 | -1.615 | -1.936 | -1.278 | too few signals |
| SUPPORT_BREAK | SHORT | 77 | 0.004 | -1.134 | -1.356 | -1.184 | -2.100 | -1.684 | -1.272 | too few signals |
| ENTRY_Q4 | LONG | 58 | 0.003 | -0.578 | -0.933 | -2.129 | -2.990 | -1.950 | -3.023 | too few signals |
| MAJOR_STRUCTURE_FAILURE | EXIT100 | 21 | 0.001 | -0.108 | -0.417 | -1.984 | -0.527 | -0.648 | -2.146 | too few signals |
| MASTER_LONG | LONG | 53 | 0.003 | -0.365 | -0.202 | -1.018 | -1.819 | -0.373 | -1.451 | too few signals |
| SMART_DISTRIBUTION | SHORT | 110 | 0.006 | -0.448 | -0.655 | -0.409 | -1.127 | -1.078 | -0.628 | no consistent edge |
| FIB_236_LONG | LONG | 182 | 0.010 | -0.205 | -0.677 | -0.555 | -1.640 | -2.240 | -1.172 | no consistent edge |
| LOWER_HIGH | SHORT | 565 | 0.032 | -0.182 | -0.375 | -0.453 | -2.193 | -2.100 | -1.561 | no consistent edge |
| HIST200_SELL | SHORT | 517 | 0.030 | -0.085 | -0.452 | -0.264 | -1.007 | -2.377 | -0.828 | no consistent edge |
| HIST1000_SELL | SHORT | 347 | 0.020 | -0.228 | -0.794 | 0.251 | -2.104 | -3.244 | 0.679 | no consistent edge |
| MAJOR_SUPPLY | EXIT100 | 347 | 0.020 | -0.228 | -0.794 | 0.251 | -2.104 | -3.244 | 0.679 | no consistent edge |
| BARRIER_L2 | EXIT25 | 1383 | 0.079 | -0.118 | -0.463 | -0.189 | -1.619 | -3.343 | -0.920 | no consistent edge |
| BOS_RETEST_SHORT | SHORT | 338 | 0.019 | 0.200 | -0.245 | -0.616 | 1.932 | -1.067 | -1.776 | no consistent edge |

## 3. Does the selected edge persist?

Out-of-sample window `2021-12-31 00:00:00` -> `2026-01-24 18:00:00`. **9 of 11** kept rules still have a positive 24h edge there.

| rule | action | signals | edge_6h | edge_24h | edge_72h | signals_oos | edge_6h_oos | edge_24h_oos | edge_72h_oos |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SWING_REVERSAL_BUY | LONG | 760 | 0.109 | 0.346 | 0.773 | 1670 | 0.013 | -0.010 | -0.269 |
| SUPPORT_MAJOR | LONG | 1358 | 0.122 | 0.325 | 0.622 | 5117 | 0.049 | 0.216 | 0.773 |
| STRUCTURE_FAILURE_SHORT | EXIT100 | 1169 | -0.065 | 0.183 | 0.678 | 2223 | 0.022 | 0.226 | 0.013 |
| PRESSURE_EXHAUSTION | EXIT50 | 1561 | 0.061 | 0.176 | 0.411 | 3303 | 0.004 | 0.070 | 0.074 |
| EMERGENCY_EXIT_04 | EXIT100 | 2284 | 0.012 | 0.251 | 0.362 | 4355 | 0.022 | 0.151 | 0.217 |
| DELTA_EXHAUSTION | EXIT50 | 1624 | 0.054 | 0.179 | 0.371 | 3364 | 0.007 | 0.084 | 0.107 |
| MASTER_FORCE_EXIT | EXIT100 | 3446 | 0.009 | 0.191 | 0.331 | 6872 | 0.009 | 0.073 | 0.087 |
| MASTER_EXIT_ALL | EXIT100 | 3446 | 0.009 | 0.191 | 0.331 | 6872 | 0.009 | 0.073 | 0.087 |
| FORCE_CLOSE | EXIT100 | 3446 | 0.009 | 0.191 | 0.331 | 6872 | 0.009 | 0.073 | 0.087 |
| EARLY_WAVE_LONG | LONG | 1881 | 0.034 | 0.197 | 0.251 | 4061 | -0.014 | -0.022 | 0.038 |
| STRUCTURE_FAILURE_LONG | EXIT100 | 1115 | 0.093 | 0.322 | 0.026 | 2132 | 0.021 | 0.072 | 0.429 |
