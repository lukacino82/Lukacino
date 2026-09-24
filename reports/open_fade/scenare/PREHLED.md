# Open ± X: momentum vs. fade × RRR 1:1 / 1:1,5 / 2:1 / 3:1

**Data:** váš Excel (`List1`, 5000-kontraktové volume bary ES, 07/2016–07/2026,
2 491 RTH dní). **Náklady** 0,5 b. ($25) na obchod, 1 ES kontrakt.

**Logiky:**
* **Momentum (otočená logika):** long stop orderem na open + X, short stop
  orderem na open − X.
* **Fade (původní):** long limitkou na open − X, short limitkou na open + X.

**RRR (TP : SL):** 1:1 = 40/40 ticků · 1:1,5 = 40/60 · 2:1 = 80/40 · 3:1 = 120/40.
Výstup TP, SL, nebo na konci seance 16:00. Oba směry nezávisle, max. 1 obchod
na směr a den.

Grafy: `heatmapa_vysledku.png` (všech 96 scénářů), `equity_momentum.png`,
`equity_fade.png`. Čísla: `souhrn.csv`. Skripty: `open_fade/scenarios.py`,
`open_fade/plot_scenarios.py`.

## Momentum: čistý výsledek za 10 let ($, t v závorce)

| X | 1:1 | 1:1,5 | 2:1 | 3:1 |
|---|---|---|---|---|
| **LONG** | | | | |
| 10 | −33,1k (−1,8) | −35,5k (−1,6) | +3,0k (0,1) | +12,9k (0,4) |
| 15 | −5,7k (−0,4) | −3,0k (−0,2) | −9,3k (−0,4) | +1,5k (0,1) |
| 20 | +4,8k (0,3) | −3,1k (−0,2) | +11,4k (0,6) | **+20,6k (0,9)** |
| 40 | −34,2k (−3,7) | −25,4k (−2,3) | −33,1k (−2,8) | −38,0k (−2,9) |
| **SHORT** | | | | |
| 10 | −53,8k (−2,9) | −35,0k (−1,6) | −66,8k (−2,6) | −57,1k (−1,9) |
| 15 | −33,8k (−2,0) | −14,5k (−0,7) | −11,0k (−0,5) | +2,5k (0,1) |
| 20 | −27,9k (−1,8) | −32,2k (−1,7) | −28,9k (−1,4) | −18,1k (−0,7) |
| 40 | −25,1k (−2,4) | −21,5k (−1,7) | −24,4k (−1,7) | −24,1k (−1,4) |
| **LONG + SHORT** | | | | |
| 10 | −86,9k (−3,3) | −70,5k (−2,2) | −63,9k (−1,8) | −44,1k (−1,1) |
| 15 | −39,5k (−1,7) | −17,6k (−0,6) | −20,3k (−0,6) | +4,0k (0,1) |
| 20 | −23,2k (−1,1) | −35,3k (−1,4) | −17,5k (−0,6) | +2,5k (0,1) |
| 40 | −59,4k (−4,2) | −46,9k (−2,8) | −57,5k (−3,1) | −62,0k (−2,9) |

## Fade: čistý výsledek za 10 let (oba směry)

| X | 1:1 | 1:1,5 | 2:1 | 3:1 |
|---|---|---|---|---|
| 10 | −101,3k | −107,8k | −99,5k | −127,3k |
| 15 | −103,6k | −118,0k | −97,8k | −80,5k |
| 20 | −96,0k | −99,6k | −85,8k | −59,0k |
| 40 | +1,6k | +4,4k | −18,0k | −28,4k |

## TP % proti break-even (oba směry)

Úspěšnost se ve všech 32 kombinacích drží ±6 procentních bodů od
break-even SL / (TP + SL). To je chování náhodné procházky: 1:1 → ~50 %,
1:1,5 → ~60 %, 2:1 → ~32 %, 3:1 → ~21 %.

## Verdikt

* **Ani jeden z 96 scénářů nemá t > 1.** Hranice statistické významnosti
  je t > 2, a při 96 pokusech spíš t > 3.
* **Momentum je méně ztrátové než fade**, protože ES v RTH krátkodobě
  mírně pokračuje ve směru prvního výraznějšího pohybu od open a fade jde
  proti tomu. Po nákladech ale ani momentum nevydělává.
* **Momentum LONG X = 20, RRR 3:1** (+$20,6k, t 0,9) je nejlepší buňka.
  Celý zisk přišel v letech 2021–2022 a jinak se křivka drží kolem nuly.
  Je to maximum z 96 pokusů, takže šum, ne hrana.
* **Shorty jsou ztrátové** v obou logikách. Trh za 10 let rostl
  z ~2 900 na ~7 800 bodů.
* **X = 40 u momenta je nejhorší** (−$59k u obou směrů). Po pohybu
  o 40 bodů od open je trh přetažený a pokračování chybí.
* Změna RRR mění jen win-rate, ne očekávanou hodnotu. Žádné nastavení
  TP/SL z náhody hranu nevyrobí.
