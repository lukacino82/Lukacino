# Pevné TP a SL po letech: long open+10 a open+15

Obchody ze studie `sierra/Lukacino_OpenX_Range_RRR.cpp` v emulaci Replay (Exit Mode Fixed TP / SL,
Long only, vstup 9:30–15:00, max. 1 obchod denně), ES 07/2016–07/2026, 1 ES, náklady 0,5 b.
Mřížka SL 5–40 b. × TP 5–80 b. (99 kombinací) × open+10/15 × Kill Yes/No = 396 běhů.
Výsledky po letech: `mrizka_po_rocich.csv`.

## 1. Nejlepší TP/SL každého roku je náhodné

Nejlepší kombinace se z roku na rok mění bez vzoru: například open+10 Kill = No
2024 SL 5 / TP 60, 2025 SL 40 / TP 20, 2026 SL 5 / TP 40.

Test bez pohledu do budoucnosti (walk-forward): v každém roce použít kombinaci,
která byla nejlepší ve všech předchozích letech. Součet 2017–2026:

| Scénář | Nejlepší zpětně (nejde zopakovat) | Walk-forward | Pevné 20 / 40 |
|---|---|---|---|
| open+10, Kill = No | +$237,5k | +$46,1k | +$56,2k |
| open+10, Kill = Yes | +$138,3k | +$24,0k | +$13,7k |
| open+15, Kill = No | +$224,8k | +$43,9k | **+$113,5k** |
| open+15, Kill = Yes | +$118,8k | +$5,7k | +$42,5k |

Výběr podle minulosti vrátí jen 5–20 % zpětně nejlepšího výsledku. Pevných 20 / 40
je ve 3 ze 4 scénářů stejně dobré nebo lepší.

## 2. TP/SL podle volatility minulého roku

Pravidlo SL = k × průměrné denní rozpětí minulého roku, TP = RRR × SL
(k 0,25 / 0,33 / 0,5, RRR 1 / 1,5 / 2 / 3): žádná z 12 variant neporazila pevných
20 / 40 u open+15 Kill = No (nejlepší +$73,1k). U ostatních scénářů jsou rozdíly
v rámci šumu.

Návrh SL = 0,5 × rozpětí minulého roku, TP = 2 × SL (Kill = No):

| Rok | Rozpětí minulého roku | SL / TP | open+10: návrh / 20-40 | open+15: návrh / 20-40 |
|---|---|---|---|---|
| 2017 | 15,4 | 7,5 / 15 | −0,9k / +10,4k | +1,1k / +8,8k |
| 2018 | 12,9 | 6,5 / 13 | −3,4k / −8,9k | +0,8k / +1,4k |
| 2019 | 33,2 | 16,5 / 33 | +15,7k / +14,3k | +9,9k / +14,3k |
| 2020 | 24,8 | 12,5 / 25 | +14,4k / +18,6k | −5,2k / +6,1k |
| 2021 | 53,0 | 26,5 / 53 | +15,1k / +36,0k | +25,4k / +26,6k |
| 2022 | 40,0 | 20 / 40 | −14,9k / −14,9k | +8,9k / +8,9k |
| 2023 | 74,4 | 37 / 74 | +16,2k / +14,3k | +20,2k / +22,9k |
| 2024 | 44,7 | 22,5 / 45 | +3,4k / +3,4k | +20,2k / +20,2k |
| 2025 | 50,2 | 25 / 50 | +16,4k / −7,5k | +20,7k / +9,2k |
| 2026 | 71,4 | 35,75 / 71,5 | −38,4k / −9,8k | −29,5k / −5,0k |
| 2027 | 74,2 (2026) | 37 / 74 | – | – |

(Mřížka měla jen vybrané hodnoty, test použil nejbližší: např. 37 / 74 → 40 / 80.)

## Závěr

* Z historie nejde vybrat TP/SL, které by příští rok vydělalo víc. Nejlepší hodnota
  roku je šum.
* Škálování podle volatility výnos nezvyšuje. Smysl má pro řízení rizika: 1 R
  (SL) odpovídá tomu, jak daleko trh v daném roce běžně chodí, a velikost pozice se
  dá nastavit na pevné $ riziko.
* Pevná vzdálenost vstupu X (10 / 15 b.) se chová stejně: v roce 2017 (rozpětí 13 b.)
  je open+15 skoro celý denní pohyb, v roce 2025 (71 b.) šum.
