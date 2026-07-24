# Signal edge analysis

period `2020-01-01 00:00:00` -> `2026-01-24 18:00:00`

## Forward return over 6h (baseline +0.041%)

| bucket | signals | mean fwd % | edge vs baseline |
| --- | ---: | ---: | ---: |
| SHORT score (0, 40] | 3866 | +0.050 | -0.009 |
| SHORT score (40, 60] | 10315 | +0.036 | +0.005 |
| SHORT score (60, 80] | 5530 | +0.069 | -0.028 |
| SHORT score (80, 101] | 2957 | +0.046 | -0.005 |
| FLAT score (0, 40] | 887 | -0.030 | -0.071 |
| FLAT score (40, 60] | 3 | +1.376 | +1.335 |
| LONG score (0, 40] | 5879 | +0.068 | +0.027 |
| LONG score (40, 60] | 12099 | +0.027 | -0.014 |
| LONG score (60, 80] | 6689 | +0.030 | -0.011 |
| LONG score (80, 101] | 4898 | +0.041 | -0.000 |

### Directional rules ranked by 6h edge

| rule | action | signals | mean fwd % | edge |
| --- | --- | ---: | ---: | ---: |
| TREND_RESUME_04 | LONG | 240 | +0.294 | +0.253 |
| SMART_ACCUMULATION | LONG | 318 | +0.292 | +0.251 |
| RESISTANCE_BREAK | LONG | 534 | +0.132 | +0.091 |
| FAILED_BOS_SHORT | LONG | 388 | +0.119 | +0.078 |
| SUPPORT_MAJOR | LONG | 6494 | +0.095 | +0.054 |
| FAILED_BOS_LONG | SHORT | 335 | -0.006 | +0.047 |
| BOS_CONTINUE_LONG | LONG | 513 | +0.086 | +0.045 |
| SWING_REVERSAL_BUY | LONG | 2431 | +0.083 | +0.042 |
| BOS_CONTINUE_SHORT | SHORT | 627 | +0.002 | +0.039 |
| HIST200_BUY | LONG | 606 | +0.080 | +0.039 |
| LOWER_LOW_CONTINUE | SHORT | 1565 | +0.006 | +0.035 |
| MARUBOZU_BEAR | SHORT | 2272 | +0.024 | +0.017 |
| HIGHER_LOW | LONG | 1879 | +0.047 | +0.006 |
| FIB_786_LONG | LONG | 2451 | +0.045 | +0.004 |
| FIB_382_SHORT | SHORT | 5899 | +0.038 | +0.003 |
| EARLY_WAVE_LONG | LONG | 5933 | +0.043 | +0.002 |
| FIB_382_LONG | LONG | 3652 | +0.041 | -0.000 |
| ENTRY_Q1 | LONG | 7603 | +0.040 | -0.001 |
| FIB_236_SHORT | SHORT | 5431 | +0.042 | -0.001 |
| ENTRY_Q2 | LONG | 3069 | +0.039 | -0.002 |
| SMART_DISTRIBUTION | SHORT | 445 | +0.047 | -0.006 |
| BULL_STRUCTURE | LONG | 28078 | +0.034 | -0.007 |
| BEAR_STRUCTURE | SHORT | 25027 | +0.049 | -0.008 |
| HIGHER_HIGH_CONTINUE | LONG | 1736 | +0.033 | -0.008 |
| FIB_236_LONG | LONG | 604 | +0.031 | -0.010 |
| BOS_RETEST_LONG | LONG | 1165 | +0.025 | -0.016 |
| FIB_786_SHORT | SHORT | 3497 | +0.059 | -0.018 |
| BUY_LIQUIDITY_GRAB | LONG | 581 | +0.023 | -0.018 |
| TREND_RESUME_01 | LONG | 679 | +0.016 | -0.025 |
| BOS_RETEST_SHORT | SHORT | 1058 | +0.068 | -0.027 |
| SHOOTING_SELL | SHORT | 2257 | +0.068 | -0.027 |
| MARUBOZU_BULL | LONG | 2261 | +0.010 | -0.031 |
| MULTI_SWING_BUY_01 | LONG | 727 | +0.006 | -0.035 |
| ENTRY_Q3 | LONG | 941 | +0.005 | -0.036 |
| TREND_RESUME_02 | LONG | 1786 | +0.004 | -0.037 |
| TREND_RESUME_03 | LONG | 1786 | +0.004 | -0.037 |
| SELL_LIQUIDITY_GRAB | SHORT | 1100 | +0.082 | -0.041 |
| DNA_DISTRIBUTION_01 | SHORT | 3025 | +0.087 | -0.046 |
| HAMMER_BUY | LONG | 1547 | -0.011 | -0.052 |
| MAJOR_DEMAND | LONG | 197 | -0.012 | -0.053 |
| HIST1000_BUY | LONG | 197 | -0.012 | -0.053 |
| MULTI_SWING_SELL_01 | SHORT | 1148 | +0.104 | -0.063 |
| LOWER_HIGH | SHORT | 1769 | +0.109 | -0.068 |
| DNA_ACCUMULATION_01 | LONG | 2077 | -0.035 | -0.076 |
| HIST200_SELL | SHORT | 1191 | +0.133 | -0.092 |
| TREND_RESUME_05 | SHORT | 272 | +0.150 | -0.109 |
| ENTRY_Q4 | LONG | 176 | -0.097 | -0.138 |
| MASTER_LONG | LONG | 199 | -0.157 | -0.198 |
| HIST1000_SELL | SHORT | 644 | +0.246 | -0.205 |
| SUPPORT_BREAK | SHORT | 300 | +0.259 | -0.218 |

## Forward return over 24h (baseline +0.165%)

| bucket | signals | mean fwd % | edge vs baseline |
| --- | ---: | ---: | ---: |
| SHORT score (0, 40] | 3865 | +0.227 | -0.063 |
| SHORT score (40, 60] | 10312 | +0.161 | +0.004 |
| SHORT score (60, 80] | 5528 | +0.184 | -0.020 |
| SHORT score (80, 101] | 2956 | +0.278 | -0.113 |
| FLAT score (0, 40] | 887 | +0.030 | -0.135 |
| FLAT score (40, 60] | 3 | +1.696 | +1.531 |
| LONG score (0, 40] | 5878 | +0.177 | +0.012 |
| LONG score (40, 60] | 12090 | +0.125 | -0.040 |
| LONG score (60, 80] | 6688 | +0.171 | +0.006 |
| LONG score (80, 101] | 4898 | +0.135 | -0.029 |

### Directional rules ranked by 24h edge

| rule | action | signals | mean fwd % | edge |
| --- | --- | ---: | ---: | ---: |
| TREND_RESUME_04 | LONG | 240 | +0.658 | +0.493 |
| RESISTANCE_BREAK | LONG | 534 | +0.488 | +0.323 |
| SMART_ACCUMULATION | LONG | 318 | +0.418 | +0.253 |
| SUPPORT_MAJOR | LONG | 6494 | +0.364 | +0.200 |
| SWING_REVERSAL_BUY | LONG | 2431 | +0.262 | +0.098 |
| MULTI_SWING_BUY_01 | LONG | 727 | +0.245 | +0.080 |
| FAILED_BOS_LONG | SHORT | 334 | +0.092 | +0.073 |
| BOS_CONTINUE_LONG | LONG | 513 | +0.226 | +0.062 |
| BOS_CONTINUE_SHORT | SHORT | 627 | +0.108 | +0.056 |
| EARLY_WAVE_LONG | LONG | 5931 | +0.208 | +0.044 |
| TREND_RESUME_01 | LONG | 679 | +0.206 | +0.042 |
| HIST200_BUY | LONG | 606 | +0.201 | +0.036 |
| FIB_236_SHORT | SHORT | 5427 | +0.133 | +0.032 |
| ENTRY_Q1 | LONG | 7602 | +0.183 | +0.018 |
| FIB_786_LONG | LONG | 2451 | +0.182 | +0.017 |
| BUY_LIQUIDITY_GRAB | LONG | 581 | +0.178 | +0.013 |
| MARUBOZU_BEAR | SHORT | 2270 | +0.160 | +0.004 |
| MARUBOZU_BULL | LONG | 2260 | +0.166 | +0.002 |
| HIGHER_HIGH_CONTINUE | LONG | 1735 | +0.159 | -0.006 |
| LOWER_LOW_CONTINUE | SHORT | 1565 | +0.177 | -0.012 |
| FIB_786_SHORT | SHORT | 3497 | +0.183 | -0.018 |
| ENTRY_Q2 | LONG | 3069 | +0.146 | -0.019 |
| BULL_STRUCTURE | LONG | 28065 | +0.144 | -0.021 |
| FAILED_BOS_SHORT | LONG | 388 | +0.141 | -0.024 |
| BEAR_STRUCTURE | SHORT | 25022 | +0.190 | -0.025 |
| DNA_DISTRIBUTION_01 | SHORT | 3024 | +0.197 | -0.032 |
| HIGHER_LOW | LONG | 1878 | +0.122 | -0.042 |
| MULTI_SWING_SELL_01 | SHORT | 1148 | +0.218 | -0.053 |
| FIB_382_LONG | LONG | 3652 | +0.106 | -0.058 |
| SHOOTING_SELL | SHORT | 2255 | +0.225 | -0.060 |
| FIB_382_SHORT | SHORT | 5898 | +0.229 | -0.065 |
| LOWER_HIGH | SHORT | 1768 | +0.253 | -0.088 |
| ENTRY_Q3 | LONG | 941 | +0.074 | -0.091 |
| TREND_RESUME_02 | LONG | 1786 | +0.071 | -0.093 |
| TREND_RESUME_03 | LONG | 1786 | +0.071 | -0.093 |
| HAMMER_BUY | LONG | 1547 | +0.067 | -0.098 |
| FIB_236_LONG | LONG | 604 | +0.054 | -0.111 |
| DNA_ACCUMULATION_01 | LONG | 2077 | +0.037 | -0.127 |
| SMART_DISTRIBUTION | SHORT | 445 | +0.304 | -0.139 |
| SELL_LIQUIDITY_GRAB | SHORT | 1100 | +0.355 | -0.190 |
| BOS_RETEST_LONG | LONG | 1165 | -0.037 | -0.202 |
| BOS_RETEST_SHORT | SHORT | 1058 | +0.372 | -0.208 |
| SUPPORT_BREAK | SHORT | 300 | +0.395 | -0.230 |
| ENTRY_Q4 | LONG | 176 | -0.118 | -0.282 |
| MASTER_LONG | LONG | 199 | -0.130 | -0.295 |
| HIST200_SELL | SHORT | 1191 | +0.517 | -0.352 |
| MAJOR_DEMAND | LONG | 197 | -0.193 | -0.357 |
| HIST1000_BUY | LONG | 197 | -0.193 | -0.357 |
| TREND_RESUME_05 | SHORT | 272 | +0.616 | -0.452 |
| HIST1000_SELL | SHORT | 644 | +0.866 | -0.701 |

## Forward return over 72h (baseline +0.491%)

| bucket | signals | mean fwd % | edge vs baseline |
| --- | ---: | ---: | ---: |
| SHORT score (0, 40] | 3864 | +0.468 | +0.023 |
| SHORT score (40, 60] | 10300 | +0.434 | +0.057 |
| SHORT score (60, 80] | 5521 | +0.355 | +0.136 |
| SHORT score (80, 101] | 2953 | +0.487 | +0.005 |
| FLAT score (0, 40] | 886 | +0.252 | -0.239 |
| FLAT score (40, 60] | 3 | -1.015 | -1.506 |
| LONG score (0, 40] | 5868 | +0.516 | +0.025 |
| LONG score (40, 60] | 12080 | +0.527 | +0.036 |
| LONG score (60, 80] | 6688 | +0.599 | +0.108 |
| LONG score (80, 101] | 4894 | +0.557 | +0.066 |

### Directional rules ranked by 72h edge

| rule | action | signals | mean fwd % | edge |
| --- | --- | ---: | ---: | ---: |
| TREND_RESUME_04 | LONG | 240 | +1.157 | +0.666 |
| SUPPORT_MAJOR | LONG | 6494 | +1.132 | +0.641 |
| RESISTANCE_BREAK | LONG | 534 | +1.118 | +0.626 |
| SMART_ACCUMULATION | LONG | 318 | +0.959 | +0.468 |
| TREND_RESUME_01 | LONG | 679 | +0.741 | +0.250 |
| BOS_RETEST_LONG | LONG | 1164 | +0.677 | +0.186 |
| DNA_DISTRIBUTION_01 | SHORT | 3021 | +0.322 | +0.169 |
| BOS_CONTINUE_LONG | LONG | 511 | +0.625 | +0.134 |
| BOS_CONTINUE_SHORT | SHORT | 627 | +0.382 | +0.110 |
| EARLY_WAVE_LONG | LONG | 5927 | +0.586 | +0.095 |
| SUPPORT_BREAK | SHORT | 300 | +0.413 | +0.078 |
| HIGHER_HIGH_CONTINUE | LONG | 1733 | +0.555 | +0.063 |
| FIB_786_SHORT | SHORT | 3491 | +0.428 | +0.063 |
| SHOOTING_SELL | SHORT | 2253 | +0.430 | +0.061 |
| MULTI_SWING_BUY_01 | LONG | 727 | +0.551 | +0.060 |
| BEAR_STRUCTURE | SHORT | 24991 | +0.447 | +0.044 |
| SWING_REVERSAL_BUY | LONG | 2431 | +0.534 | +0.043 |
| BULL_STRUCTURE | LONG | 28048 | +0.528 | +0.037 |
| MARUBOZU_BULL | LONG | 2256 | +0.527 | +0.036 |
| FAILED_BOS_SHORT | LONG | 388 | +0.526 | +0.035 |
| FIB_786_LONG | LONG | 2444 | +0.525 | +0.034 |
| ENTRY_Q1 | LONG | 7596 | +0.523 | +0.032 |
| FIB_236_SHORT | SHORT | 5425 | +0.478 | +0.014 |
| LOWER_LOW_CONTINUE | SHORT | 1564 | +0.493 | -0.001 |
| SMART_DISTRIBUTION | SHORT | 445 | +0.507 | -0.016 |
| HIGHER_LOW | LONG | 1877 | +0.466 | -0.026 |
| ENTRY_Q3 | LONG | 941 | +0.460 | -0.031 |
| ENTRY_Q2 | LONG | 3068 | +0.444 | -0.048 |
| FIB_236_LONG | LONG | 603 | +0.440 | -0.051 |
| LOWER_HIGH | SHORT | 1766 | +0.583 | -0.092 |
| MARUBOZU_BEAR | SHORT | 2265 | +0.586 | -0.095 |
| FIB_382_SHORT | SHORT | 5893 | +0.589 | -0.097 |
| TREND_RESUME_05 | SHORT | 272 | +0.596 | -0.105 |
| SELL_LIQUIDITY_GRAB | SHORT | 1100 | +0.602 | -0.111 |
| HAMMER_BUY | LONG | 1546 | +0.375 | -0.116 |
| TREND_RESUME_02 | LONG | 1786 | +0.363 | -0.128 |
| TREND_RESUME_03 | LONG | 1786 | +0.363 | -0.128 |
| FAILED_BOS_LONG | SHORT | 332 | +0.624 | -0.133 |
| FIB_382_LONG | LONG | 3650 | +0.333 | -0.159 |
| MULTI_SWING_SELL_01 | SHORT | 1148 | +0.674 | -0.182 |
| DNA_ACCUMULATION_01 | LONG | 2075 | +0.249 | -0.242 |
| BOS_RETEST_SHORT | SHORT | 1058 | +0.737 | -0.246 |
| BUY_LIQUIDITY_GRAB | LONG | 579 | +0.238 | -0.254 |
| MASTER_LONG | LONG | 199 | +0.036 | -0.455 |
| HIST1000_SELL | SHORT | 644 | +0.963 | -0.471 |
| HIST200_BUY | LONG | 606 | -0.014 | -0.505 |
| HIST200_SELL | SHORT | 1191 | +1.050 | -0.559 |
| ENTRY_Q4 | LONG | 176 | -0.349 | -0.840 |
| HIST1000_BUY | LONG | 197 | -0.598 | -1.089 |
| MAJOR_DEMAND | LONG | 197 | -0.598 | -1.089 |
