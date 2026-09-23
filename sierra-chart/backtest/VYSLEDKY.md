# Backtest: Previous Session High Breakout na ES (1min, 07/2018 – 09/2026)

Data: `ES3000.txt` (main, 2,9 mil. 1min barů, čas ET). Skript: `backtest_psh.py` – replikuje logiku studie
(režim Custom Time Window, max 1 obchod za session, SL = low předchozí session, flatten ve Flatten Time).
1 kontrakt, $50/bod, náklady $25 na obchod. Když bar zasáhne SL i TP, počítá se SL.
Plnění `live` = vstup PSH + 1 tick (jako v reálném čase), `close` = close průrazového baru (jako bar-based backtest SC).

| Setup (ET) | RR | obchodů | win % | net USD | USD/obchod | t | PF | max DD | riziko (b.) | výstup TP / SL / čas % |
|---|---|---|---|---|---|---|---|---|---|---|
| A: 18:00–9:30 → 9:30–11:30, flat 11:25 | 1.0 | 997 | 51.1 | −11 250 | −11.3 | −0.37 | 0.97 | −30 912 | 29.5 | 6 / 9 / 85 |
| A | 1.5 | 997 | 50.7 | −19 675 | −19.7 | −0.68 | 0.94 | −30 569 | 29.5 | 2 / 9 / 90 |
| A2: 18:00–9:30 → 9:30–16:00, flat 15:55 | 1.0 | 1262 | 52.5 | +48 438 | +38.4 | 1.01 | 1.08 | −33 888 | 30.2 | 18 / 20 / 62 |
| A2 | 1.5 | 1262 | 51.3 | +54 569 | +43.2 | 1.10 | 1.09 | −32 731 | 30.2 | 6 / 21 / 73 |
| B: 9:30–10:00 → 10:00–12:00, flat 11:55 | 1.0 | 1355 | 52.8 | −11 012 | −8.1 | −0.39 | 0.97 | −28 975 | 15.5 | 20 / 23 / 58 |
| B | 1.5 | 1355 | 52.1 | +5 100 | +3.8 | 0.17 | 1.01 | −24 825 | 15.5 | 8 / 23 / 69 |
| C: předchozí RTH den 9:30–16:00 | 1.0 | 930 | 53.3 | +4 725 | +5.1 | 0.11 | 1.01 | −34 900 | 40.8 | 9 / 13 / 78 |
| C | 1.5 | 930 | 52.6 | −1 456 | −1.6 | −0.03 | 1.00 | −35 231 | 40.8 | 2 / 14 / 84 |
| D: Daily, session grafu 18:00–17:00, flat 15:55 | 1.0 | 1146 | 52.4 | −37 100 | −32.4 | −0.66 | 0.95 | −77 925 | 51.6 | 8 / 13 / 78 |
| D | 1.5 | 1146 | 52.1 | −10 769 | −9.4 | −0.18 | 0.98 | −72 888 | 51.6 | 3 / 13 / 84 |

Srovnání: prostý long 9:30 → 15:55 každý den = +$23 175 ($11/den, t 0.27).

Po letech (net USD, live):

| rok | A RR1.5 | A2 RR1.0 | A2 RR1.5 | B RR1.5 | C RR1.5 | D RR1.5 |
|---|---|---|---|---|---|---|
| 2018 (od 7/2018) | −8 462 | −16 062 | −14 388 | −5 031 | −13 838 | −1 750 |
| 2019 | +119 | +2 200 | +1 062 | +1 606 | +4 812 | +19 488 |
| 2020 | −6 175 | +22 312 | +23 750 | −7 975 | −8 894 | −4 019 |
| 2021 | +17 781 | +21 900 | +25 069 | +7 506 | −838 | +5 838 |
| 2022 | −15 038 | −20 075 | −17 456 | −14 269 | +16 531 | +13 800 |
| 2023 | −819 | +9 975 | +5 775 | +1 919 | +1 844 | −6 006 |
| 2024 | −2 144 | −1 350 | −3 506 | +8 081 | −5 294 | −7 800 |
| 2025 | −2 269 | +34 000 | +32 725 | +8 525 | −1 350 | −36 031 |
| 2026 (do 9/2026) | −2 669 | −4 462 | +1 538 | +4 738 | +5 569 | +5 712 |

## Závěr
* Žádná varianta nemá statisticky prokázanou hranu (všechna |t| < 2). Nejlepší A2 (t ≈ 1.1) je vybraná
  z 20 testovaných variant a je slabší než náhoda by vysvětlila.
* Nastavení A (obchodování jen do 11:30) je po nákladech ztrátové: stop na overnight low (~30 b.) je na
  2 hodiny moc daleko, 85–90 % obchodů končí časem.
* Daily (D) má stop na low celého předchozího dne (~52 b. = $2 600 na kontrakt) a drawdown −$73k.

Pozn.: první verze tohoto reportu měla chybu v převodu data (okna přes půlnoc se slučovala) – čísla
výše jsou po opravě. Okna, která nepřechází půlnoc (B, C), se nezměnila.
