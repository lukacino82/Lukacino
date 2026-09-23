# ES: analýza hrany v nejvolatilnějších oknech seance

* Soubor: `ES3000.txt`, surových barů: 2,895,557
* Období: 2018-07-08 18:00:00-04:00 → 2026-09-23 12:40:00-04:00 (2,560 dní)
* Analyzováno na 5min barech, náklady 0.5 bodu na round-trip (ES tick 0.25 = 12.5 USD)

## Přehled

| strategie | obchodů | win% | E[R] | t | PF | rand p | DSR | OOS E[R] | OOS t | kontroly |
|---|---|---|---|---|---|---|---|---|---|---|
| ORB 30m | 1282 | 39.626 | 0.054 | 1.396 | 1.096 | 0.065 | 0.340 | 0.100 | 2.221 | 3 |
| ORB 5m | 2102 | 28.164 | -0.065 | -1.799 | 0.915 | 0.219 | 0.000 | -0.051 | -1.214 | 1.000 |
| ORB 15m | 1216 | 34.539 | 0.052 | 1.128 | 1.077 | 0.070 | 0.247 | 0.078 | 1.467 | 2 |
| ORB fade (sweep) | 1108 | 43.773 | -0.009 | -0.276 | 0.982 | 0.204 | 0.019 | -0.100 | -2.685 | 1.000 |
| Intraday momentum | 2018 | 45.540 | -0.030 | -3.431 | 0.809 | 0.945 | 0.000 | -0.028 | -2.495 | 1.000 |
| Gap fade | 613 | 45.188 | 0.132 | 2.499 | 1.247 | 0.010 | 0.762 | 0.104 | 1.947 | 6 |
| Europe open breakout | 1604 | 45.449 | -0.019 | -1.232 | 0.922 | 0.224 | 0.001 | -0.046 | -2.510 | 1.000 |

`rand p` = p-hodnota testu náhodného směru, `DSR` = Deflated Sharpe (korigováno na počet vyzkoušených variant), `OOS` = walk-forward mimo vzorek (750 dní trénink / 250 dní test).

## 1. Kde je trh nejživější (ET, 30min okna)

`rel_range` = průměrný range baru vůči průměru dne (1.0 = průměr).

| ET | rel_range | abs_ret_bp | bars | rank |
|---|---|---|---|---|
| 09:30 | 2.307 | 9.005 | 12703 | 1.000 |
| 10:00 | 2.045 | 8.003 | 12708 | 2 |
| 15:30 | 1.846 | 7.693 | 12276 | 3 |
| 10:30 | 1.788 | 6.951 | 12708 | 4 |
| 11:00 | 1.620 | 6.342 | 12708 | 5 |
| 11:30 | 1.485 | 5.737 | 12708 | 6 |
| 15:00 | 1.466 | 5.917 | 12276 | 7 |
| 14:00 | 1.421 | 5.661 | 12276 | 8 |
| 14:30 | 1.406 | 5.676 | 12276 | 9 |
| 12:00 | 1.357 | 5.307 | 12708 | 10 |
| 13:00 | 1.317 | 5.289 | 12326 | 11 |
| 12:30 | 1.286 | 5.026 | 12705 | 12 |

|  | avg_range_pct |
|---|---|
| Po | 1.373 |
| Út | 1.440 |
| St | 1.567 |
| Čt | 1.588 |
| Pá | 1.464 |
| Ne | 0.571 |

## ORB 30m

Nejlepší varianta z 16 pokusů: `{'max_range_atr': np.float64(0.35)}` + `{'rrr': np.float64(3.0), 'max_trades_per_day': np.float64(1.0)}`

* obchodů 1282, win-rate 39.6%, E[R] 0.054, t 1.40, PF 1.10, max DD 48.2 R
* bootstrap 95% CI E[R]: [-0.021, 0.128]
* náhodný směr: p = 0.065 (null průměr 0.001)
* Deflated Sharpe (16 pokusů): 0.340
* **Walk-forward OOS**: 922 obchodů, E[R] 0.100, t 2.221
* Verdikt: **BEZ PROKAZATELNÉ HRANY (3/7).**

Kontroly: ✔ expectancy > 0 po nákladech, ✘ t-stat > 2, ✘ bootstrap 95% CI nad nulou, ✘ lepší než náhodný směr (p < 0.05), ✘ Deflated Sharpe > 0.95, ✔ kladná většina let, ✔ >= 100 obchodů

Po letech:

| date | trades | win_rate | expectancy_r | total_r |
|---|---|---|---|---|
| 2018 | 68 | 0.353 | -0.009 | -0.617 |
| 2019 | 164 | 0.335 | -0.093 | -15.237 |
| 2020 | 172 | 0.378 | -0.076 | -13.093 |
| 2021 | 144 | 0.424 | 0.088 | 12.692 |
| 2022 | 138 | 0.457 | 0.234 | 32.266 |
| 2023 | 171 | 0.409 | 0.134 | 22.931 |
| 2024 | 179 | 0.408 | 0.103 | 18.482 |
| 2025 | 154 | 0.370 | 0.058 | 8.991 |
| 2026 | 92 | 0.435 | 0.030 | 2.764 |

## ORB 5m

Nejlepší varianta z 16 pokusů: `{'max_range_atr': np.float64(10.0)}` + `{'rrr': np.float64(3.0), 'max_trades_per_day': np.float64(1.0)}`

* obchodů 2102, win-rate 28.2%, E[R] -0.065, t -1.80, PF 0.91, max DD 152.5 R
* bootstrap 95% CI E[R]: [-0.137, 0.005]
* náhodný směr: p = 0.219 (null průměr -0.091)
* Deflated Sharpe (16 pokusů): 0.000
* **Walk-forward OOS**: 1368 obchodů, E[R] -0.051, t -1.214
* Verdikt: **BEZ PROKAZATELNÉ HRANY (1/7).**

Kontroly: ✘ expectancy > 0 po nákladech, ✘ t-stat > 2, ✘ bootstrap 95% CI nad nulou, ✘ lepší než náhodný směr (p < 0.05), ✘ Deflated Sharpe > 0.95, ✘ kladná většina let, ✔ >= 100 obchodů

Po letech:

| date | trades | win_rate | expectancy_r | total_r |
|---|---|---|---|---|
| 2018 | 110 | 0.218 | -0.294 | -32.391 |
| 2019 | 258 | 0.283 | -0.157 | -40.612 |
| 2020 | 257 | 0.265 | -0.126 | -32.479 |
| 2021 | 258 | 0.349 | 0.175 | 45.171 |
| 2022 | 258 | 0.302 | 0.035 | 9.119 |
| 2023 | 257 | 0.253 | -0.116 | -29.919 |
| 2024 | 259 | 0.259 | -0.119 | -30.900 |
| 2025 | 257 | 0.296 | -0.014 | -3.622 |
| 2026 | 188 | 0.271 | -0.113 | -21.171 |

## ORB 15m

Nejlepší varianta z 16 pokusů: `{'range_end': '09:45', 'entry_end': '11:30', 'max_range_atr': np.float64(0.25)}` + `{'rrr': np.float64(3.0), 'max_trades_per_day': np.int64(1)}`

* obchodů 1216, win-rate 34.5%, E[R] 0.052, t 1.13, PF 1.08, max DD 39.6 R
* bootstrap 95% CI E[R]: [-0.036, 0.141]
* náhodný směr: p = 0.070 (null průměr -0.010)
* Deflated Sharpe (16 pokusů): 0.247
* **Walk-forward OOS**: 878 obchodů, E[R] 0.078, t 1.467
* Verdikt: **BEZ PROKAZATELNÉ HRANY (2/7).**

Kontroly: ✔ expectancy > 0 po nákladech, ✘ t-stat > 2, ✘ bootstrap 95% CI nad nulou, ✘ lepší než náhodný směr (p < 0.05), ✘ Deflated Sharpe > 0.95, ✘ kladná většina let, ✔ >= 100 obchodů

Po letech:

| date | trades | win_rate | expectancy_r | total_r |
|---|---|---|---|---|
| 2018 | 66 | 0.273 | -0.133 | -8.798 |
| 2019 | 143 | 0.315 | -0.033 | -4.650 |
| 2020 | 162 | 0.340 | -0.100 | -16.227 |
| 2021 | 136 | 0.404 | 0.248 | 33.732 |
| 2022 | 128 | 0.398 | 0.285 | 36.540 |
| 2023 | 154 | 0.312 | 0.015 | 2.370 |
| 2024 | 174 | 0.305 | -0.011 | -1.895 |
| 2025 | 164 | 0.348 | 0.030 | 4.866 |
| 2026 | 89 | 0.427 | 0.190 | 16.885 |

## ORB fade (sweep)

Nejlepší varianta z 16 pokusů: `{'min_excursion_atr': np.float64(0.1)}` + `{'rrr': np.float64(1.5), 'max_trades_per_day': np.float64(2.0)}`

* obchodů 1108, win-rate 43.8%, E[R] -0.009, t -0.28, PF 0.98, max DD 71.7 R
* bootstrap 95% CI E[R]: [-0.073, 0.055]
* náhodný směr: p = 0.204 (null průměr -0.035)
* Deflated Sharpe (16 pokusů): 0.019
* **Walk-forward OOS**: 875 obchodů, E[R] -0.100, t -2.685
* Verdikt: **BEZ PROKAZATELNÉ HRANY (1/7).**

Kontroly: ✘ expectancy > 0 po nákladech, ✘ t-stat > 2, ✘ bootstrap 95% CI nad nulou, ✘ lepší než náhodný směr (p < 0.05), ✘ Deflated Sharpe > 0.95, ✘ kladná většina let, ✔ >= 100 obchodů

Po letech:

| date | trades | win_rate | expectancy_r | total_r |
|---|---|---|---|---|
| 2018 | 78 | 0.474 | 0.081 | 6.333 |
| 2019 | 142 | 0.451 | -0.037 | -5.255 |
| 2020 | 127 | 0.480 | 0.098 | 12.488 |
| 2021 | 114 | 0.447 | -0.062 | -7.099 |
| 2022 | 137 | 0.365 | -0.125 | -17.155 |
| 2023 | 133 | 0.338 | -0.248 | -33.039 |
| 2024 | 147 | 0.469 | 0.081 | 11.849 |
| 2025 | 125 | 0.504 | 0.187 | 23.341 |
| 2026 | 105 | 0.429 | -0.016 | -1.641 |

## Intraday momentum

Nejlepší varianta z 4 pokusů: `{'min_move_atr': np.float64(0.0)}` + `{'target_mode': 'none', 'rrr': np.float64(2.0)}`

* obchodů 2018, win-rate 45.5%, E[R] -0.030, t -3.43, PF 0.81, max DD 65.0 R
* bootstrap 95% CI E[R]: [-0.047, -0.013]
* náhodný směr: p = 0.945 (null průměr -0.017)
* Deflated Sharpe (4 pokusů): 0.000
* **Walk-forward OOS**: 1145 obchodů, E[R] -0.028, t -2.495
* Verdikt: **BEZ PROKAZATELNÉ HRANY (1/7).**

Kontroly: ✘ expectancy > 0 po nákladech, ✘ t-stat > 2, ✘ bootstrap 95% CI nad nulou, ✘ lepší než náhodný směr (p < 0.05), ✘ Deflated Sharpe > 0.95, ✘ kladná většina let, ✔ >= 100 obchodů

Po letech:

| date | trades | win_rate | expectancy_r | total_r |
|---|---|---|---|---|
| 2018 | 103 | 0.447 | -0.050 | -5.114 |
| 2019 | 245 | 0.469 | -0.038 | -9.314 |
| 2020 | 250 | 0.420 | -0.045 | -11.125 |
| 2021 | 250 | 0.400 | -0.083 | -20.627 |
| 2022 | 249 | 0.478 | -0.032 | -7.862 |
| 2023 | 247 | 0.478 | 0.002 | 0.572 |
| 2024 | 247 | 0.478 | -0.017 | -4.109 |
| 2025 | 246 | 0.476 | -0.004 | -0.953 |
| 2026 | 181 | 0.448 | -0.016 | -2.925 |

## Gap fade

Nejlepší varianta z 16 pokusů: `{'min_gap_atr': np.float64(0.2)}` + `{'rrr': np.float64(2.0), 'max_trades_per_day': np.float64(2.0)}`

* obchodů 613, win-rate 45.2%, E[R] 0.132, t 2.50, PF 1.25, max DD 17.9 R
* bootstrap 95% CI E[R]: [0.030, 0.237]
* náhodný směr: p = 0.010 (null průměr -0.008)
* Deflated Sharpe (16 pokusů): 0.762
* **Walk-forward OOS**: 381 obchodů, E[R] 0.104, t 1.947
* Verdikt: **SLIBNÉ, NEPROKÁZANÉ (6/7).**

Kontroly: ✔ expectancy > 0 po nákladech, ✔ t-stat > 2, ✔ bootstrap 95% CI nad nulou, ✔ lepší než náhodný směr (p < 0.05), ✘ Deflated Sharpe > 0.95, ✔ kladná většina let, ✔ >= 100 obchodů

Po letech:

| date | trades | win_rate | expectancy_r | total_r |
|---|---|---|---|---|
| 2018 | 29 | 0.586 | 0.511 | 14.818 |
| 2019 | 69 | 0.493 | 0.137 | 9.461 |
| 2020 | 94 | 0.457 | 0.097 | 9.110 |
| 2021 | 87 | 0.425 | 0.040 | 3.460 |
| 2022 | 64 | 0.453 | 0.175 | 11.186 |
| 2023 | 75 | 0.453 | 0.238 | 17.872 |
| 2024 | 72 | 0.431 | 0.117 | 8.426 |
| 2025 | 69 | 0.493 | 0.270 | 18.649 |
| 2026 | 54 | 0.333 | -0.219 | -11.829 |

## Europe open breakout

Nejlepší varianta z 16 pokusů: `{'range_start': '00:00', 'range_end': '08:00', 'entry_end': '10:00'}` + `{'rrr': np.float64(2.0), 'max_trades_per_day': np.int64(1)}`

* obchodů 1604, win-rate 45.4%, E[R] -0.019, t -1.23, PF 0.92, max DD 59.1 R
* bootstrap 95% CI E[R]: [-0.051, 0.012]
* náhodný směr: p = 0.224 (null průměr -0.032)
* Deflated Sharpe (16 pokusů): 0.001
* **Walk-forward OOS**: 1203 obchodů, E[R] -0.046, t -2.510
* Verdikt: **BEZ PROKAZATELNÉ HRANY (1/7).**

Kontroly: ✘ expectancy > 0 po nákladech, ✘ t-stat > 2, ✘ bootstrap 95% CI nad nulou, ✘ lepší než náhodný směr (p < 0.05), ✘ Deflated Sharpe > 0.95, ✘ kladná většina let, ✔ >= 100 obchodů

Po letech:

| date | trades | win_rate | expectancy_r | total_r |
|---|---|---|---|---|
| 2018 | 86 | 0.453 | -0.008 | -0.731 |
| 2019 | 182 | 0.456 | 0.063 | 11.505 |
| 2020 | 175 | 0.503 | 0.070 | 12.262 |
| 2021 | 190 | 0.447 | -0.057 | -10.780 |
| 2022 | 207 | 0.459 | -0.007 | -1.393 |
| 2023 | 237 | 0.435 | -0.087 | -20.541 |
| 2024 | 205 | 0.463 | -0.073 | -14.956 |
| 2025 | 188 | 0.447 | -0.020 | -3.756 |
| 2026 | 134 | 0.425 | -0.020 | -2.652 |

## Podmíněné analýzy

### ORB 30m

| směr | trades | win_rate | expectancy_r | t_stat |
|---|---|---|---|---|
| long | 705 | 0.417 | 0.040 | 0.818 |
| short | 577 | 0.371 | 0.071 | 1.151 |

| den | trades | win_rate | expectancy_r | t_stat |
|---|---|---|---|---|
| Friday | 225 | 0.431 | 0.157 | 1.662 |
| Monday | 267 | 0.423 | 0.070 | 0.892 |
| Thursday | 231 | 0.390 | 0.044 | 0.479 |
| Tuesday | 271 | 0.432 | 0.125 | 1.453 |
| Wednesday | 288 | 0.316 | -0.101 | -1.234 |

| ATR kvintil (volatilita režimu) | trades | win_rate | expectancy_r | t_stat |
|---|---|---|---|---|
| (16.91, 37.025] | 257 | 0.354 | -0.075 | -0.888 |
| (37.025, 49.046] | 256 | 0.367 | -0.012 | -0.137 |
| (49.046, 61.093] | 256 | 0.410 | 0.189 | 2.005 |
| (61.093, 76.975] | 256 | 0.418 | 0.093 | 1.097 |
| (76.975, 242.554] | 257 | 0.432 | 0.075 | 0.941 |

| riziko/ATR kvintil | trades | win_rate | expectancy_r | t_stat |
|---|---|---|---|---|
| (0.0351, 0.182] | 257 | 0.381 | 0.065 | 0.698 |
| (0.182, 0.227] | 256 | 0.395 | 0.166 | 1.748 |
| (0.227, 0.263] | 256 | 0.375 | -0.034 | -0.405 |
| (0.263, 0.304] | 256 | 0.410 | 0.044 | 0.543 |
| (0.304, 0.35] | 257 | 0.420 | 0.029 | 0.368 |

| čas vstupu | trades | win_rate | expectancy_r | t_stat |
|---|---|---|---|---|
| 10:00 | 1158 | 0.401 | 0.069 | 1.667 |
| 10:30 | 85 | 0.365 | -0.019 | -0.141 |
| 11:00 | 29 | 0.379 | -0.210 | -1.265 |
| 11:30 | 10 | 0.200 | -0.310 | -1.492 |

MFE kvantily (R): {0.25: 0.35, 0.5: 0.84, 0.75: 1.81, 0.9: 2.95}; MAE medián 1.00 R

### ORB 5m

| směr | trades | win_rate | expectancy_r | t_stat |
|---|---|---|---|---|
| long | 1066 | 0.299 | -0.014 | -0.265 |
| short | 1036 | 0.264 | -0.118 | -2.311 |

| den | trades | win_rate | expectancy_r | t_stat |
|---|---|---|---|---|
| Friday | 415 | 0.304 | 0.040 | 0.470 |
| Monday | 421 | 0.292 | -0.057 | -0.705 |
| Thursday | 422 | 0.268 | -0.138 | -1.767 |
| Tuesday | 423 | 0.303 | 0.019 | 0.229 |
| Wednesday | 421 | 0.242 | -0.188 | -2.412 |

| ATR kvintil (volatilita režimu) | trades | win_rate | expectancy_r | t_stat |
|---|---|---|---|---|
| (16.302999999999997, 35.489] | 421 | 0.299 | -0.066 | -0.821 |
| (35.489, 47.739] | 420 | 0.293 | -0.016 | -0.195 |
| (47.739, 60.475] | 420 | 0.260 | -0.120 | -1.506 |
| (60.475, 76.129] | 420 | 0.286 | -0.028 | -0.343 |
| (76.129, 242.554] | 421 | 0.271 | -0.095 | -1.199 |

| riziko/ATR kvintil | trades | win_rate | expectancy_r | t_stat |
|---|---|---|---|---|
| (0.016999999999999998, 0.109] | 421 | 0.238 | -0.210 | -2.601 |
| (0.109, 0.142] | 420 | 0.236 | -0.193 | -2.430 |
| (0.142, 0.173] | 420 | 0.307 | 0.035 | 0.423 |
| (0.173, 0.222] | 420 | 0.312 | 0.049 | 0.593 |
| (0.222, 0.824] | 421 | 0.316 | -0.006 | -0.071 |

| čas vstupu | trades | win_rate | expectancy_r | t_stat |
|---|---|---|---|---|
| 09:30 | 2084 | 0.280 | -0.068 | -1.879 |
| 10:00 | 17 | 0.471 | 0.238 | 0.607 |
| 10:30 | 1.000 | 1.000 | 1.438 | nan |

MFE kvantily (R): {0.25: 0.3, 0.5: 0.87, 0.75: 2.55, 0.9: 3.0}; MAE medián 1.00 R

### ORB 15m

| směr | trades | win_rate | expectancy_r | t_stat |
|---|---|---|---|---|
| long | 650 | 0.386 | 0.121 | 1.948 |
| short | 566 | 0.299 | -0.028 | -0.406 |

| den | trades | win_rate | expectancy_r | t_stat |
|---|---|---|---|---|
| Friday | 213 | 0.352 | 0.107 | 0.956 |
| Monday | 254 | 0.362 | 0.023 | 0.247 |
| Thursday | 218 | 0.303 | -0.058 | -0.532 |
| Tuesday | 258 | 0.388 | 0.168 | 1.659 |
| Wednesday | 273 | 0.319 | 0.012 | 0.122 |

| ATR kvintil (volatilita režimu) | trades | win_rate | expectancy_r | t_stat |
|---|---|---|---|---|
| (17.052999999999997, 38.768] | 245 | 0.302 | -0.110 | -1.113 |
| (38.768, 50.107] | 242 | 0.331 | 0.079 | 0.728 |
| (50.107, 61.911] | 243 | 0.342 | 0.060 | 0.579 |
| (61.911, 77.286] | 243 | 0.391 | 0.133 | 1.315 |
| (77.286, 242.554] | 243 | 0.362 | 0.097 | 0.970 |

| riziko/ATR kvintil | trades | win_rate | expectancy_r | t_stat |
|---|---|---|---|---|
| (0.0243, 0.139] | 244 | 0.283 | -0.142 | -1.412 |
| (0.139, 0.172] | 243 | 0.321 | 0.024 | 0.229 |
| (0.172, 0.197] | 243 | 0.366 | 0.204 | 1.901 |
| (0.197, 0.222] | 243 | 0.337 | -0.033 | -0.345 |
| (0.222, 0.391] | 243 | 0.420 | 0.206 | 2.014 |

| čas vstupu | trades | win_rate | expectancy_r | t_stat |
|---|---|---|---|---|
| 09:30 | 1069 | 0.334 | 0.036 | 0.725 |
| 10:00 | 135 | 0.437 | 0.199 | 1.496 |
| 10:30 | 9 | 0.222 | -0.227 | -0.467 |
| 11:00 | 3 | 0.667 | -0.039 | -0.075 |

MFE kvantily (R): {0.25: 0.31, 0.5: 0.94, 0.75: 2.31, 0.9: 3.0}; MAE medián 1.00 R

### ORB fade (sweep)

| směr | trades | win_rate | expectancy_r | t_stat |
|---|---|---|---|---|
| long | 587 | 0.445 | -0.013 | -0.278 |
| short | 521 | 0.430 | -0.005 | -0.110 |

| den | trades | win_rate | expectancy_r | t_stat |
|---|---|---|---|---|
| Friday | 229 | 0.380 | -0.133 | -1.847 |
| Monday | 193 | 0.508 | 0.153 | 1.937 |
| Thursday | 238 | 0.429 | -0.032 | -0.437 |
| Tuesday | 214 | 0.439 | -0.023 | -0.314 |
| Wednesday | 234 | 0.444 | 0.014 | 0.184 |

| ATR kvintil (volatilita režimu) | trades | win_rate | expectancy_r | t_stat |
|---|---|---|---|---|
| (16.837999999999997, 34.461] | 222 | 0.441 | -0.077 | -1.064 |
| (34.461, 45.786] | 222 | 0.414 | -0.079 | -1.071 |
| (45.786, 58.664] | 221 | 0.425 | -0.027 | -0.359 |
| (58.664, 74.618] | 221 | 0.434 | 0.041 | 0.544 |
| (74.618, 234.446] | 222 | 0.473 | 0.096 | 1.292 |

| riziko/ATR kvintil | trades | win_rate | expectancy_r | t_stat |
|---|---|---|---|---|
| (0.127, 0.175] | 222 | 0.396 | -0.061 | -0.761 |
| (0.175, 0.214] | 221 | 0.443 | 0.042 | 0.525 |
| (0.214, 0.265] | 222 | 0.396 | -0.075 | -0.985 |
| (0.265, 0.347] | 221 | 0.480 | 0.035 | 0.482 |
| (0.347, 2.428] | 222 | 0.473 | 0.014 | 0.229 |

| čas vstupu | trades | win_rate | expectancy_r | t_stat |
|---|---|---|---|---|
| 10:00 | 271 | 0.347 | -0.208 | -2.975 |
| 10:30 | 293 | 0.457 | 0.045 | 0.661 |
| 11:00 | 189 | 0.444 | -0.006 | -0.080 |
| 11:30 | 145 | 0.469 | 0.038 | 0.438 |
| 12:00 | 121 | 0.463 | 0.064 | 0.701 |
| 12:30 | 89 | 0.551 | 0.236 | 2.271 |

MFE kvantily (R): {0.25: 0.33, 0.5: 0.82, 0.75: 1.5, 0.9: 1.5}; MAE medián 0.86 R

### Intraday momentum

| směr | trades | win_rate | expectancy_r | t_stat |
|---|---|---|---|---|
| long | 1123 | 0.451 | -0.036 | -3.287 |
| short | 895 | 0.461 | -0.023 | -1.603 |

| den | trades | win_rate | expectancy_r | t_stat |
|---|---|---|---|---|
| Friday | 399 | 0.454 | -0.019 | -0.939 |
| Monday | 383 | 0.444 | -0.045 | -2.424 |
| Thursday | 407 | 0.452 | -0.052 | -2.560 |
| Tuesday | 414 | 0.461 | -0.029 | -1.591 |
| Wednesday | 415 | 0.465 | -0.008 | -0.393 |

| ATR kvintil (volatilita režimu) | trades | win_rate | expectancy_r | t_stat |
|---|---|---|---|---|
| (16.302999999999997, 35.546] | 404 | 0.423 | -0.054 | -2.460 |
| (35.546, 47.925] | 403 | 0.462 | -0.045 | -2.047 |
| (47.925, 60.639] | 404 | 0.463 | -0.037 | -1.957 |
| (60.639, 76.407] | 403 | 0.462 | 0.004 | 0.212 |
| (76.407, 242.554] | 404 | 0.468 | -0.020 | -1.134 |

| riziko/ATR kvintil | trades | win_rate | expectancy_r | t_stat |
|---|---|---|---|---|
| (0.499999999999983, 0.499999999999996] | 408 | 0.429 | -0.042 | -2.139 |
| (0.499999999999996, 0.499999999999999] | 400 | 0.472 | -0.027 | -1.391 |
| (0.499999999999999, 0.500000000000001] | 415 | 0.455 | -0.031 | -1.595 |
| (0.500000000000001, 0.500000000000004] | 409 | 0.447 | -0.030 | -1.586 |
| (0.500000000000004, 0.500000000000016] | 386 | 0.474 | -0.021 | -0.977 |

| čas vstupu | trades | win_rate | expectancy_r | t_stat |
|---|---|---|---|---|
| 15:30 | 2018 | 0.455 | -0.030 | -3.431 |

MFE kvantily (R): {0.25: 0.1, 0.5: 0.22, 0.75: 0.38, 0.9: 0.58}; MAE medián 0.21 R

### Gap fade

| směr | trades | win_rate | expectancy_r | t_stat |
|---|---|---|---|---|
| long | 264 | 0.455 | 0.094 | 1.212 |
| short | 349 | 0.450 | 0.162 | 2.231 |

| den | trades | win_rate | expectancy_r | t_stat |
|---|---|---|---|---|
| Friday | 136 | 0.478 | 0.240 | 2.047 |
| Monday | 115 | 0.452 | 0.014 | 0.130 |
| Thursday | 125 | 0.456 | 0.193 | 1.603 |
| Tuesday | 112 | 0.500 | 0.261 | 2.044 |
| Wednesday | 125 | 0.376 | -0.052 | -0.456 |

| ATR kvintil (volatilita režimu) | trades | win_rate | expectancy_r | t_stat |
|---|---|---|---|---|
| (16.837999999999997, 34.407] | 123 | 0.520 | 0.260 | 2.186 |
| (34.407, 45.379] | 122 | 0.434 | 0.082 | 0.690 |
| (45.379, 57.971] | 123 | 0.455 | 0.188 | 1.546 |
| (57.971, 75.368] | 122 | 0.451 | 0.112 | 0.943 |
| (75.368, 222.321] | 123 | 0.398 | 0.020 | 0.170 |

| riziko/ATR kvintil | trades | win_rate | expectancy_r | t_stat |
|---|---|---|---|---|
| (0.0161, 0.142] | 123 | 0.480 | 0.311 | 2.320 |
| (0.142, 0.198] | 122 | 0.402 | 0.096 | 0.744 |
| (0.198, 0.272] | 123 | 0.415 | 0.074 | 0.617 |
| (0.272, 0.386] | 122 | 0.459 | 0.069 | 0.643 |
| (0.386, 1.143] | 123 | 0.504 | 0.111 | 1.128 |

| čas vstupu | trades | win_rate | expectancy_r | t_stat |
|---|---|---|---|---|
| 09:30 | 613 | 0.452 | 0.132 | 2.499 |

MFE kvantily (R): {0.25: 0.47, 0.5: 1.06, 0.75: 2.0, 0.9: 2.0}; MAE medián 0.92 R

### Europe open breakout

| směr | trades | win_rate | expectancy_r | t_stat |
|---|---|---|---|---|
| long | 897 | 0.480 | -0.018 | -0.948 |
| short | 707 | 0.421 | -0.021 | -0.798 |

| den | trades | win_rate | expectancy_r | t_stat |
|---|---|---|---|---|
| Friday | 313 | 0.466 | -0.019 | -0.555 |
| Monday | 324 | 0.466 | -0.012 | -0.372 |
| Thursday | 307 | 0.450 | -0.037 | -1.048 |
| Tuesday | 334 | 0.440 | -0.006 | -0.165 |
| Wednesday | 326 | 0.451 | -0.024 | -0.671 |

| ATR kvintil (volatilita režimu) | trades | win_rate | expectancy_r | t_stat |
|---|---|---|---|---|
| (13.249, 34.571] | 322 | 0.450 | -0.006 | -0.161 |
| (34.571, 45.629] | 320 | 0.416 | -0.077 | -2.085 |
| (45.629, 58.132] | 320 | 0.516 | 0.042 | 1.138 |
| (58.132, 75.043] | 321 | 0.458 | -0.034 | -1.045 |
| (75.043, 263.696] | 321 | 0.433 | -0.022 | -0.637 |

| riziko/ATR kvintil | trades | win_rate | expectancy_r | t_stat |
|---|---|---|---|---|
| (0.07339999999999999, 0.216] | 321 | 0.445 | -0.054 | -1.220 |
| (0.216, 0.283] | 321 | 0.452 | 0.001 | 0.037 |
| (0.283, 0.356] | 320 | 0.456 | -0.008 | -0.227 |
| (0.356, 0.474] | 321 | 0.436 | -0.026 | -0.877 |
| (0.474, 2.53] | 321 | 0.483 | -0.010 | -0.438 |

| čas vstupu | trades | win_rate | expectancy_r | t_stat |
|---|---|---|---|---|
| 08:00 | 1042 | 0.458 | -0.033 | -1.564 |
| 08:30 | 273 | 0.458 | -0.013 | -0.366 |
| 09:00 | 184 | 0.397 | -0.016 | -0.437 |
| 09:30 | 105 | 0.514 | 0.088 | 1.760 |

MFE kvantily (R): {0.25: 0.16, 0.5: 0.35, 0.75: 0.7, 0.9: 1.12}; MAE medián 0.38 R

## Intradenní struktura (RTH)

Korelace výnosu poslední půlhodiny (15:30–16:00) s dřívějšími okny (kladná = momentum, záporná = reverze):

* ON: +0.049  (n=2045)
* 09:30: -0.018  (n=2046)
* ON+first30: +0.039  (n=2045)
* 10:00: +0.096  (n=2046)
* 15:00: +0.051  (n=2046)
* první půlhodina vs. zbytek dne: -0.015


_Výpočet trval 5.2 min._