# Cyklové levely (BCL / Leverage levels) na ES 2018–2026

Kód: `grid_data.py` (mřížka a data), `levels_test.py` (hlavní test), `m4_robust.py` (robustnost).
Výsledky jsou v `out/`.

## Mřížka (zrekonstruovaná z popisků weekly grafu US500Cash)
- **Červené levely** (celé cykly) jsou geometrické: R_k = 2908,44 × 1,38944^k. Řada: 2093,26 · 2908,44 · 4041,07 · 5614,79 · 7801,36 · 10839,6.
- **Dělení cyklu:** každý cyklus mezi dvěma červenými je lineárně rozdělený na čtvrtiny:
  - 1/4 fialová;
  - 1/2 bílá nebo žlutá;
  - 3/4 modrá.
  
  Například 5614,79 / 6161,43 / 6708,08 / 7254,72 / 7801,36. Mřížka sedí na všechny popisky grafu.
- **Indikátory .ex4** (BCL_big_cycle_lines, 09_Leverage_levels, © Domogled s.r.o.) jsou zkompilované a zašifrované. Zdrojový kód z nich přečíst nejde. Test proto používá rekonstrukci, která přesně sedí na graf.

## Data a převod na cash
- **Data:** surová (ne back-adjusted) 1min data předního kontraktu ES, 2018-07 až 2026-09.
- **Převod na cash:** přes fair value, F / (1 + (sazba − dividenda) × T).
- **Kontrola:** dna a vrcholy 2020 a 2022 sedí na S&P cash s chybou ±10 bodů. Na grafu je mezi levely 200–550 bodů.

## Metodika
- **Hustota mřížky m:** m = 4 je mřížka z grafu. Jemnější m = 8, 16, 32, 64 jsou intradenní levely, rozestup ≈ 34 bodů při m = 64.
- **Událost:** první dotek levelu poté, co cena byla aspoň 0,5 rozestupu od něj. Vstup přesně na levelu.
- **Výsledek:** co přijde dřív – odraz zpět, nebo průraz skrz, o 0,25 / 0,5 / 1 / 2 rozestupy.
  - Fade: TP zpět, SL skrz. Breakout je zrcadlo.
  - Všech 16 kombinací TP/SL, tedy RRR určené levely. Náklad 0,5 bodu.
- **Nulový model:** 200 stejných mřížek s náhodnou fází, tj. všechny levely posunuté o náhodný zlomek cyklu. p = podíl náhodných mřížek se stejným nebo lepším výsledkem.

## Výsledky

### Odraz o 0,5 rozestupu dřív než průraz o 0,5 rozestupu
| Mřížka | Doteků | Odraz | Nulový model | p |
|---|---|---|---|---|
| m = 4 (graf, rozestup 200–550 b.) | 89 | **59,6 %** | 51,2 % | **0,010** |
| m = 8 | 341 | 50,4 % | 49,8 % | 0,35 |
| m = 16 | 1 280 | 49,2 % | 49,3 % | 0,54 |
| m = 32 | 4 516 | 49,6 % | 49,3 % | 0,32 |
| m = 64 (≈ 34 b.) | 15 190 | 49,4 % | 49,1 % | 0,18 |

### Robustnost m = 4
| Test | Skutečná mřížka | Nulový model | p |
|---|---|---|---|
| Odraz 0,25 rozestupu | 48,3 % | 51,4 % | 0,78 |
| **Odraz 0,5 rozestupu** | **59,6 %** | 51,2 % | **0,01** |
| Odraz 1 rozestup | 36,0 % | 39,0 % | 0,72 |
| 0,5 bez shluků (1 událost / 10 dní, n = 62) | 54,8 % | 46,5 % | 0,035 |
| 0,5, 2018–21 | 60,0 % | 54,4 % | 0,055 |
| 0,5, 2022–26 | 59,1 % | 47,4 % | 0,03 |
| Fade TP 0,5 / SL 0,5 (R/obchod) | +0,21 R | +0,04 R | 0,005 |

### Typy levelů (m = 4, odraz 0,5)
| Typ | n | Odraz | Nulový model | p |
|---|---|---|---|---|
| červená (cyklus) | 26 | 65 % | 52 % | 0,03 |
| 1/2 | 19 | 63 % | 51 % | 0,04 |
| 1/4 a 3/4 | 44 | 55 % | 51 % | 0,26 |

### Všechny konfigurace dohromady
Fade a breakout jsou zrcadla, nezávislých kombinací je tedy 80 (5 hustot × 16 TP/SL). Z nich je 8 na hladině 10 %, což přesně odpovídá náhodě.
- Breakout varianty jsou na m = 4 spíš horší než nulový model.
- Na jemných mřížkách je všechno v šumu.

### Dokončení cyklu
Test: cena dosáhne 3/4, vrátí se na 1/2 – dokončí cyklus?
- Celý červený cyklus: jen 3 případy, netestovatelné.
- Pod-cykly (1/4 a 1/16 cyklu): nahoru se dokončí v 95–99 % případů, ale náhodné mřížky dávají 94–98 %. Je to jen rostoucí trh, ne vlastnost levelů.
- Dolů je výsledek stejný jako u nulového modelu.

## Závěr
- **Intradenní levely** (jemné dělení m = 8–64, rozestup 34–270 bodů) nemají žádný efekt: 21 300 doteků, odraz = náhoda.
- **Velké levely z grafu** (červené a poloviny) ukazují zatím nejzajímavější náznak z celého výzkumu: odraz 60–65 % proti 51 % u náhodných mřížek (p 0,01–0,04), v obou obdobích. Fade s TP i SL 0,5 rozestupu (≈ 200–270 bodů) +0,21 R na obchod.
- **Prokázané to není:**
  1. Jen 89 doteků (62 nezávislých) za 8 let.
  2. Efekt je jen u jedné vzdálenosti (0,5). Při 0,25 a 1 rozestupu zmizí.
  3. Celkový počet významných konfigurací (8 z 80 na hladině 10 %) odpovídá náhodě.
  4. Mřížka byla nakreslená až po pohledu na graf; ukotvení mohlo být zvolené podle historických otoček.
- **Dokončování cyklů** se od náhody neliší.
- **Další krok:** test na delší historii, která je pro tuto mřížku mimo vzorek. Stačí export US500Cash D1/H1 z MT4 (od roku 2000) a případně stejné indikátory na jiných trzích. Pokud efekt na 2000–2018 vydrží, má smysl z toho stavět systém (fade na červených a polovičních levelech, TP/SL podle levelů).
