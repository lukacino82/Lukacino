# Test „Lukacino Buy Weakness“ na ES 07/2016–07/2026

Logika navržené studie: rozhodnutí v 15:58 ET, denní RTH market profile (POC, VAH, VAL 70 %) z volume barů, RSI(2) Wilder, MA200/MA5 z denních close v 15:58, max. 1 pozice, náklady 0,5 b. na obchod, 1 ES. Skripty: `analysis/buy_weakness/backtest.py`, `report.py`. Grafy: `equity_1es.png`, `ucet.png`.

**Náhoda** = stejný počet obchodů se stejnou délkou držení, ale v náhodné dny (2 000×). p = podíl náhodných pokusů, které byly stejně dobré nebo lepší. **Nová data** = období, které původní výzkum neviděl (VAL: 07/2016–07/2018, RSI(2): 07/2016–05/2019).

## Varianty (rozhodnutí 15:58)

| Varianta | Obchodů | Win | b./obchod | t | Náhoda b./obch | p | 2016–21 t | 2022–26 t | Nová data b./obch | Max DD | Nejhorší |
|---|---|---|---|---|---|---|---|---|---|---|---|
| VAL swing (výzkum: bez stopu, max 10 dní) | 256 | 80 % | 12,0 | 2,49 | 7,7 | 0,21 | 3,18 | 1,08 | 1,3 (46) | −$33,7k | −380 b. |
| VAL swing + stop 3×ATR | 290 | 75 % | 3,9 | 0,77 | 5,8 | 0,65 | 0,87 | 0,38 | −1,8 (54) | −$55,9k | −293 b. |
| VAL swing + stop 2,5×ATR | 302 | 72 % | 2,7 | 0,58 | 5,3 | 0,72 | 1,48 | −0,15 | 0,6 (56) | −$80,3k | −244 b. |
| VAL swing jen nad MA200 | 199 | 81 % | 8,5 | 1,66 | 7,7 | 0,46 | 2,40 | 0,54 | −3,0 (28) | −$28,4k | −380 b. |
| VAL swing max 5 dní | 302 | 70 % | 9,3 | 2,48 | 5,2 | 0,17 | 2,92 | 1,06 | −1,7 (57) | −$38,1k | −356 b. |
| VAL swing + add-on | 256 | 82 % | 18,5 | 2,48 | 7,7 | 0,02 | 3,31 | 1,05 | 5,4 (46) | −$46,9k | −729 b. |
| RSI(2)<10 nad MA200 (výzkum) | 76 | 74 % | 25,4 | 3,61 | 5,4 | 0,01 | 2,09 | 2,97 | −0,8 (15) | −$12,0k | −151 b. |
| RSI(2)<10 + stop 3×ATR | 89 | 70 % | 17,3 | 2,32 | 4,2 | 0,03 | 1,86 | 1,49 | 0,8 (20) | −$13,9k | −168 b. |
| RSI(2)<5 nad MA200 | 43 | 77 % | 32,0 | 3,19 | 5,3 | 0,01 | 1,14 | 3,39 | −7,0 (8) | −$10,8k | −143 b. |
| RSI(2)<20 nad MA200 | 130 | 72 % | 13,7 | 2,66 | 5,7 | 0,12 | 1,54 | 2,19 | −1,3 (24) | −$17,2k | −251 b. |
| Obě (1 pozice, první signál) | 248 | 81 % | 14,9 | 3,20 | 7,3 | 0,08 | 2,94 | 1,94 | −3,9 (46) | −$29,4k | −302 b. |
| Obě + stop 3×ATR | 294 | 75 % | 6,5 | 1,28 | 5,5 | 0,41 | 1,15 | 0,80 | −8,9 (55) | −$55,7k | −293 b. |

## Citlivost na čas rozhodnutí (16:00 místo 15:58)

| Varianta | Obchodů | b./obchod | t | p proti náhodě |
|---|---|---|---|---|
| VAL swing (výzkum: bez stopu, max 10 dní) | 176 | 13,0 | 2,20 | 0,09 |
| VAL swing + stop 3×ATR | 185 | 9,7 | 1,72 | 0,13 |
| VAL swing + stop 2,5×ATR | 186 | 11,3 | 2,18 | 0,08 |
| VAL swing jen nad MA200 | 130 | 6,8 | 1,00 | 0,42 |
| VAL swing max 5 dní | 190 | 14,5 | 3,09 | 0,01 |
| VAL swing + add-on | 176 | 17,1 | 2,29 | 0,02 |
| RSI(2)<10 nad MA200 (výzkum) | 79 | 24,6 | 3,59 | 0,01 |
| RSI(2)<10 + stop 3×ATR | 90 | 18,5 | 2,54 | 0,02 |
| RSI(2)<5 nad MA200 | 44 | 34,1 | 3,31 | 0,01 |
| RSI(2)<20 nad MA200 | 126 | 12,7 | 2,43 | 0,15 |
| Obě (1 pozice, první signál) | 206 | 16,2 | 3,05 | 0,02 |
| Obě + stop 3×ATR | 230 | 11,7 | 2,31 | 0,04 |

## Simulace účtu $50 000 v MES (reinvestice, páka = hodnota kontraktů / účet)

| Plán | Konec | CAGR | Max DD |
|---|---|---|---|
| Konzervativní: RSI(2), páka 1× | $66,141 | 2,8 % | −4 % |
| Konzervativní: Obě, páka 1× | $88,905 | 5,9 % | −11 % |
| Agresivní: Obě, páka 3×, brzdy −20 %/−30 % | $165,624 | 12,7 % | −33 % |
| Buy & hold, páka 1× | ~$128 000 | ~9,9 % | −28 % |

## Závěr

* **RSI(2) < 10 nad MA200 je jediná hrana, která test prošla:** +25 b./obchod, t 3,6, nad náhodou +20 b. (p = 0,01), kladná 2016–21 i 2022–26, prahy 5 / 10 / 20 všechny kladné, stejný výsledek při rozhodnutí v 15:58 i 16:00. Slabina: jen ~8 obchodů ročně a na nových datech 2016–05/2019 (15 obchodů) ≈ 0.
* **VAL swing se nepotvrdil.** Na 1min profilu 2018–2026 (období, kde byl nalezen) dával +23 b. a p = 0,009. Na volume barech a 10 letech +12 b., nad náhodou jen +4 b., p = 0,21 (16:00: p = 0,09). Na nových datech 2016–2018 ≈ +1 b. Výsledek je citlivý na přesnost profilu a čas close, to je znak přeučení, ne robustní hrany.
* **Katastrofický stop 2,5–3 × ATR škodí oběma** (VAL z +12 na +3–4 b., RSI z +25 na +17 b.). Tyto hrany žijí z toho, že pozice přečká pokles.
* **Obě dohromady:** +15 b., t 3,2, p = 0,08. Zisk táhne hlavně RSI(2) a obecný růst.
* **Účet:** konzervativní plány mají malý drawdown (−4 až −11 %), ale roční výnos 3–6 %, tedy méně než buy & hold (jsou v trhu jen část času). Agresivní plán (páka 3×) vydělal 12,7 % ročně při max. DD −33 %.
