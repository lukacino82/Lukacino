# Backtest: Previous Session High Breakout na ES (1min, 07/2018 – 09/2026)

Data: `ES3000.txt` (main, 2,9 mil. 1min barů, čas ET). Skript: `backtest_psh.py` – replikuje logiku studie
(režim Custom Time Window, max 1 obchod za session, SL = low předchozí session, flatten ve Flatten Time).
1 kontrakt, $50/bod, náklady $25 na obchod. Když bar zasáhne SL i TP, počítá se SL.
Plnění `live` = vstup PSH + 1 tick (jako v reálném čase), `close` = close průrazového baru (jako bar-based backtest SC).

| Setup (ET) | RR | obchodů | win % | net USD | USD/obchod | t | PF | max DD | riziko (b.) | výstup TP / SL / čas % |
|---|---|---|---|---|---|---|---|---|---|---|
| A: 18:00–9:30 → 9:30–11:30, flat 11:25 | 1.0 | 1091 | 50.8 | +5 138 | +4.7 | 0.17 | 1.01 | −22 975 | 24.2 | 11 / 13 / 76 |
| A | 1.5 | 1091 | 50.2 | +4 569 | +4.2 | 0.15 | 1.01 | −21 988 | 24.2 | 3 / 13 / 84 |
| A2: 18:00–9:30 → 9:30–16:00, flat 15:55 | 1.0 | 1360 | 52.6 | +42 212 | +31.0 | 0.92 | 1.07 | −29 962 | 24.8 | 26 / 25 / 49 |
| **A2** | **1.5** | 1360 | 51.0 | **+78 825** | **+58.0** | **1.60** | 1.13 | −24 994 | 24.8 | 12 / 26 / 62 |
| B: 9:30–10:00 → 10:00–12:00, flat 11:55 | 1.0 | 1355 | 52.8 | −11 012 | −8.1 | −0.39 | 0.97 | −28 975 | 15.5 | 20 / 23 / 58 |
| B | 1.5 | 1355 | 52.1 | +5 100 | +3.8 | 0.17 | 1.01 | −24 825 | 15.5 | 8 / 23 / 69 |
| C: předchozí RTH den 9:30–16:00 | 1.0 | 930 | 53.3 | +4 725 | +5.1 | 0.11 | 1.01 | −34 900 | 40.8 | 9 / 13 / 78 |
| C | 1.5 | 930 | 52.6 | −1 456 | −1.6 | −0.03 | 1.00 | −35 231 | 40.8 | 2 / 14 / 84 |

Srovnání: prostý long 9:30 → 15:55 každý den = +$23 175 ($11/den, t 0.27).
Stejné vstupy jako A2 držené do 15:55 bez SL/TP = +$49 962 ($37/obchod, t 0.80).

Po letech (net USD, live):

| rok | A RR1.5 | A2 RR1.0 | A2 RR1.5 | B RR1.5 | C RR1.5 |
|---|---|---|---|---|---|
| 2018 (od 7/2018) | −8 550 | −9 838 | −9 544 | −5 031 | −13 838 |
| 2019 | +2 094 | +1 388 | +3 106 | +1 606 | +4 812 |
| 2020 | −3 975 | +11 625 | +15 244 | −7 975 | −8 894 |
| 2021 | +20 050 | +26 275 | +34 806 | +7 506 | −838 |
| 2022 | −8 188 | −14 562 | −4 281 | −14 269 | +16 531 |
| 2023 | −1 156 | +9 338 | +14 169 | +1 919 | +1 844 |
| 2024 | −544 | +375 | −1 738 | +8 081 | −5 294 |
| 2025 | +1 094 | +22 500 | +24 112 | +8 525 | −1 350 |
| 2026 (do 9/2026) | +3 744 | −4 888 | +2 950 | +4 738 | +5 569 |

## Závěr
* Žádná varianta nemá statisticky prokázanou hranu (všechna t < 2). Nejlepší A2 RR 1.5 (t = 1.6)
  je vybraná z 16 testovaných variant, takže jde spíš o náhodu nebo zachycení dlouhodobého růstu ES.
* Doporučené nastavení A (obchodování jen do 11:30) je po nákladech kolem nuly: stop na overnight low
  (~24 b. = $1 200) je na 2 hodiny moc daleko, 76–84 % obchodů končí časem.
* Obchodování přes celý den (A2) vychází lépe, ale drawdown −$25 až −30k na 1 kontrakt a ztrátové roky
  2018, 2022, 2024.
