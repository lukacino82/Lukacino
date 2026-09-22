# Výsledky backtestu – ORB RRR na ES

Data: ES kontinuální kontrakt, export ze Sierra Chart (1min → převedeno na 5min, `--resample 5`),
14. 7. 2024 – 22. 9. 2026, čas New York, 1 kontrakt, $50/bod, poplatek $4 round-trip.
Nastavení: OR 9:30–9:45, vstupy do 11:30, flatten 15:55, SL = opačná strana range.
In-sample = 7/2024 – 1/2026, out-of-sample = 2/2026 – 9/2026 (posledních 30 % dat).
Slippage **není** započtený.

| RRR | Obchody IS / OOS | Win IS / OOS | Net IS | Net OOS | PF IS / OOS | Max DD OOS |
|---|---|---|---|---|---|---|
| 1:0.5 | 393 / 168 | 71 % / 63 % | +$23 491 | −$3 185 | 1.20 / 0.96 | −$22 587 |
| 1:1   | 393 / 168 | 54 % / 52 % | +$32 741 | +$4 991 | 1.19 / 1.05 | −$19 767 |
| **1:1.5** | 393 / 168 | 48 % / 48 % | **+$57 028** | **+$7 291** | **1.30 / 1.07** | −$19 049 |
| 1:2   | 393 / 168 | 44 % / 45 % | +$40 928 | +$6 391 | 1.20 / 1.06 | −$23 628 |
| 1:3   | 393 / 168 | 43 % / 43 % | +$48 628 | −$5 422 | 1.24 / 0.95 | −$27 011 |

Po pololetích (RRR 1:1.5): 2024H2 +$18.3k · 2025H1 +$34.2k · 2025H2 +$5.2k · 2026H1 +$8.4k · 2026H2 −$1.7k.

Závěr: edge v in-sample, v out-of-sample výrazně slábne (PF ~1.05). Zatím nevhodné na live.

Reprodukce:
```bash
python backtest/orb_backtest.py data/es_5min.txt --resample 5 --sweep 0.5 1 1.5 2 3 --oos 0.3
```
