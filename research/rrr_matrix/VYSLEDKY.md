# RRR matice: SL 6–100 bodů × RRR 1:1–1:25, časová okna, série ztrát, ATR, stop-hunty, sonda, ML (ES 2011–2026)

**Kód:**
- `engine.py` – jeden průchod 1min daty na vstup dá výsledek všech kombinací;
- `analysis.py` – části A–E;
- `part2.py` – části F–H.

Výsledky jsou v `out/`. Data: ES 1min 2011-01 – 2026-09, tj. 15,7 roku. Delta (bid/ask objem) je k dispozici od roku 2011.

## Nastavení
- **Vstupy:** každou celou hodinu, všech 23 hodin Globexu, long i short. 93 666 vstupů na směr a horizont.
- **Horizont** (= „timeframe“ obchodu):
  - intraday: do 16:59 ET téhož dne;
  - 5 dní;
  - 20 dní.
- **SL v bodech:** 6, 8, 10, 12, 15, 20, 25, 30, 40, 50, 60, 80, 100. TP = SL × RRR, RRR 1 / 1,5 / 2 / 3 / 5 / 10 / 15 / 20 / 25.
- **SL v ATR:** 0,25–3 × ATR z timeframe horizontu (intraday ATR14 hodinových barů, 5D denní ATR14, 20D týdenní ATR14), TP dopočtený z RRR.
- **Náklady:** 0,5 bodu na obchod (komise + skluz).
- **Pořadí v baru:** SL i TP ve stejné minutě = ztráta (konzervativně). Obchod, který do konce horizontu nedosáhl SL ani TP, se zavře na close.

## A. Základní tabulka (vstup každou hodinu, bez podmínky)

| Horizont | Směr | SL | RRR | Win % | Win % náhodné ceny 1/(1+RRR) | Uzavřeno časem | R/obchod | R 2011–18 | R 2019–26 |
|---|---|---|---|---|---|---|---|---|---|
| intraday | long | 6 | 1,5 | 32,4 | 40,0 | 18 % | −0,050 | −0,038 | −0,064 |
| intraday | long | 10 | 3 | 9,5 | 25,0 | 45 % | −0,005 | −0,010 | 0,000 |
| intraday | long | 20 | 10 | 0,0 | 9,1 | 72 % | +0,009 | −0,001 | +0,021 |
| intraday | short | 6 | 1,5 | 31,1 | 40,0 | 17 % | −0,128 | −0,134 | −0,120 |
| intraday | short | 20 | 3 | 4,6 | 25,0 | 69 % | −0,053 | −0,048 | −0,058 |
| 5D | long | 20 | 1,5 | 32,8 | 40,0 | 18 % | +0,048 | +0,055 | +0,040 |
| 5D | long | 10 | 20 | 0,5 | 4,8 | 22 % | +0,071 | +0,019 | +0,125 |
| 20D | long | 20 | 10 | 3,4 | 9,1 | 20 % | +0,163 | +0,135 | +0,192 |
| 20D | long | 100 | 1,5 | 17,3 | 40,0 | 52 % | +0,112 | +0,104 | +0,121 |
| 20D | short | 20 | 10 | 5,0 | 9,1 | 9 % | −0,249 | −0,325 | −0,170 |

**Co z toho plyne:**
1. **Win rate odpovídá náhodné ceně.** U obchodů, které doběhnou do SL nebo TP, je P(TP dřív než SL) ≈ SL/(SL+TP). Žádné RRR samo nic nepřidá.
2. **Vyšší RRR nemá samo o sobě výhodu:**
   - u intraday 1:10–1:25 skoro nikdy nedojde na TP (výhry 0–0,4 %) a obchod se zavře časem;
   - výsledek je pak jen pohyb ceny do konce dne minus náklady;
   - u 5–20 dní je long kladný jen díky růstu indexu: je to forma buy & hold s pákou, ne edge.
3. **Menší timeframe = horší.**
   - intraday long: od −0,05 R (SL 6) po +0,01 R;
   - intraday short: −0,01 až −0,13 R;
   - malý SL (6–10 b.) platí 5–8 % R na nákladech a ve stejné minutě ho trh trefí často.
4. **Short:** záporný na všech horizontech a SL (proti driftu).
5. **ATR místo pevných bodů** odstraní to, že 10 bodů v roce 2011 (ES 1300) znamenalo něco jiného než v roce 2026 (ES 7800). Edge ale nevytvoří, vzorec je stejný:
   - intraday long od −0,42 R (0,25 ATR, náklady) po −0,002 R (3 ATR);
   - 20D long +0,03 až +0,20 R (drift);
   - short záporný.

## B. Optimální hodina, den, měsíc
Pro každou kombinaci se vybralo nejlepší okno na letech 2011–18 a změřil se výsledek v letech 2019–26:

| Okno | Long intraday: zlepšení OOS | Kombinací s lepším OOS | Poznámka |
|---|---|---|---|
| hodina | +0,020 R | 92 % | vybírají se 19:00 a 23:00 ET, tj. noční drift (už známý efekt) |
| den v týdnu | −0,023 R | 18 % | nedrží |
| měsíc | +0,002 R (5D long −0,27 R) | 70 % / 1 % | výběr měsíce je přeučení |

**Short:** výběr hodiny 2011–18 OOS nepomáhá (lepší jen v 1–33 % kombinací).

Jediné, co drží, je noční drift: long otevřený večer v Globexu. To je známý tokový efekt, od roku 2021 slábne (viz bod 9 v `ZAVERY.md`).

## C. Série ztrát
Jedna pozice najednou, další vstup v nejbližší celou hodinu po uzavření. Tabulka je `out/C_streaks.csv` pro všechny kombinace.

| Horizont | SL | RRR | Obchodů/rok | Win % | Max. série | Max. série při stejné win % náhodně | Série ≥ 10 | Série ≥ 20 | Série ≥ 50 |
|---|---|---|---|---|---|---|---|---|---|
| intraday | 10 | 1,5 | 1 283 | 32,3 | 33 | 24 | 166 | 18 | 0 |
| intraday | 10 | 3 | 917 | 15,3 | 261 | 49 | 307 | 69 | 16 |
| intraday | 20 | 3 | 487 | 7,3 | 1 194 | 91 | 166 | 69 | 13 |
| intraday | 6 | 10 | 1 015 | 3,1 | 2 028 | 218 | 311 | 201 | 58 |
| 5D | 20 | 1,5 | 422 | 39,3 | 15 | 16 | 20 | 0 | 0 |
| 5D | 20 | 3 | 250 | 21,8 | 169 | 29 | 54 | 9 | 3 |
| 20D | 20 | 3 | 228 | 26,2 | 24 | 24 | 39 | 2 | 0 |
| 20D | 10 | 10 | 276 | 9,3 | 57 | 66 | 160 | 59 | 2 |
| 20D | 40 | 10 | 35 | 2,7 | 225 | 117 | 9 | 7 | 2 |

**Co z toho plyne:**
- Při nízkém RRR (1–1,5) a delším horizontu jsou série jako u náhody: max. 13–33 v řadě.
- **Vysoké RRR s pevnými body dává série o řád delší než náhoda** (261 místo 49, 2 028 místo 218). V klidných letech TP v bodech prostě nikdy nedojde. Pevné body nejsou stacionární, proto nutně ATR.

## D. Minimální počet ziskových obchodů (náklad 0,5 b.)
Breakeven win rate = (1 + náklad/SL) / (1 + RRR):

| RRR | SL 6 b.: z 10 / 100 / 1000 | SL 20 b.: z 10 / 100 / 1000 | SL 100 b.: z 10 / 100 / 1000 |
|---|---|---|---|
| 1:1 | 6 / 55 / 542 | 6 / 52 / 513 | 6 / 51 / 503 |
| 1:1,5 | 5 / 44 / 434 | 5 / 41 / 410 | 5 / 41 / 402 |
| 1:2 | 4 / 37 / 362 | 4 / 35 / 342 | 4 / 34 / 335 |
| 1:3 | 3 / 28 / 271 | 3 / 26 / 257 | 3 / 26 / 252 |
| 1:5 | 2 / 19 / 181 | 2 / 18 / 171 | 2 / 17 / 168 |
| 1:10 | 1 / 10 / 99 | 1 / 10 / 94 | 1 / 10 / 92 |
| 1:15 | 1 / 7 / 68 | 1 / 7 / 65 | 1 / 7 / 63 |
| 1:20 | 1 / 6 / 52 | 1 / 5 / 49 | 1 / 5 / 48 |
| 1:25 | 1 / 5 / 42 | 1 / 4 / 40 | 1 / 4 / 39 |

U 10 obchodů je číslo zaokrouhlené nahoru. Například 1:25 potřebuje 0,4 výhry z 10, tedy prakticky 1 ze 25. Úplná tabulka pro všechny SL je v `out/D_min_winners.csv`.

**Skutečnost:** intradenní 1:10 až 1:25 mají reálnou win rate 0–3 %, tedy pod hranicí. U horizontu 20 dní se hranice dosáhne jen díky růstu indexu.

## E. Alfa proti buy & hold (výběr 2011–18, test 2019–26, riziko 1 % na obchod)

| Výběr | SL | RRR | Obchodů 2019–26 | R/obchod | CAGR | maxDD | Alfa/rok | t |
|---|---|---|---|---|---|---|---|---|
| ATR 20D long | 0,25 ATR týdne | 20 | 412 | +0,23 | 9,8 % | −45 % | +9,2 % | 1,09 |
| ATR 5D long | 2 ATR dne | 1,5 | 471 | +0,06 | 3,6 % | −9 % | +2,1 % | 1,05 |
| body 5D long | 25 b. | 2 | 3 145 | +0,02 | 5,4 % | −45 % | −7,0 % | −1,1 |
| body 20D long | 6 b. | 20 | 4 712 | +0,03 | −37 % | −99,5 % | −24 % | −0,7 |
| body intraday long | 20 b. | 1 | 9 014 | −0,005 | −10 % | −76 % | −24 % | −3,4 |
| B&H ES | – | – | – | – | 11,3 % | – | – | – |

**Žádná kombinace nemá alfu ≥ 3 % s t ≥ 2.**
- Nejlepší (ATR 20D long) má alfu +9 % ročně, ale t = 1,1 a DD −45 %. To je statisticky šum.
- Pevný malý SL s rizikem 1 % účtu na obchod znamená obrovskou páku: SL 6 b. ≈ 6× páka. Účet se zničí, i když je R/obchod kladné.

## F. Stop-hunt hypotéza („algoritmy nejdřív vyberou stopy retailu“)
- **Signál:** v RTH průraz předchozího denního low (nebo nočního low) o ≥ 1 bod a návrat close nad úroveň do 30 minut, potom long. Zrcadlově short u high.
- **Varianty:**
  - kumulativní delta během sweepu ve směru obchodu / proti;
  - denní bias (close nad 200denním průměrem);
  - bias + delta;
  - SL za extrémem sweepu.
- **Srovnání:** náhodný vstup téhož dne až po čase signálu. První verze srovnání brala i minuty před signálem, tedy i pokles, který ke sweepu teprve vedl, a vycházela tak falešně dobře. Je opravená.

| Úroveň | Směr | Varianta | n | R (průměr přes SL × RRR) | Náhodný vstup | Rozdíl | Max t |
|---|---|---|---|---|---|---|---|
| předchozí den low | long | vše | 889 | −0,050 | −0,046 | −0,004 | 0,2 |
| předchozí den low | long | bias + delta | 349 | −0,013 | −0,046 | +0,033 | 1,6 |
| předchozí den low | long | delta ve směru | 421 | −0,055 | −0,046 | −0,009 | 0,6 |
| noční low | long | vše | 1 576 | −0,033 | −0,042 | +0,009 | −0,1 |
| noční low | long | bias + delta | 479 | −0,042 | −0,042 | −0,001 | 0,1 |
| předchozí den high | short | vše | 988 | −0,005 | −0,036 | +0,031 | 0,7 |
| noční high | short | delta ve směru | 608 | −0,023 | −0,056 | +0,034 | −0,1 |

- **Vstup po sweepu** je stejný jako náhodný vstup v témže dni. Rozdíl −0,04 až +0,05 R, max t 1,6.
- **Kumulativní delta** nic konzistentně nepřidává.
- **SL těsně za extrémem sweepu** (≈ 4–7 b.) je záporný: −0,07 až −0,28 R.

Hypotéza, že po vybrání stopů přijde pohyb správným směrem, data ES 2011–26 nepotvrzují. Edge Factory ani Alpha Audit ji dříve také nepotvrdily.

## G. Sondovací pozice vs. přímý vstup vs. průměrování dolů
Long, vstupy každou hodinu, SL/TP měřeno od skutečného vstupu.

| Horizont | SL | RRR | Přímý vstup | Sonda: reálná až po +0,25 SL | Sonda: po +0,5 SL | Limit níž o 0,25 SL | Limit níž o 0,5 SL |
|---|---|---|---|---|---|---|---|
| intraday | 10 | 1,5 | −0,017 | −0,039 | −0,046 | −0,010 | −0,011 |
| intraday | 20 | 3 | +0,008 | +0,001 | +0,005 | +0,002 | −0,010 |
| 5D | 20 | 3 | +0,065 | +0,043 | +0,046 | +0,064 | +0,062 |
| 5D | 10 | 10 | +0,060 | +0,042 | +0,039 | +0,059 | +0,050 |

- **Potvrzení sondou výsledek zhoršuje** o 0,01–0,03 R: vstupuje se dráž a ES má krátkodobý návrat k průměru.
- **Vstup níž** (limit, princip průměrování) je zhruba stejný jako přímý vstup, edge nepřidá.
- **Skutečné průměrování** se společným stopem zvyšuje riziko v nejhorších případech, proto ho nedoporučuji.

## H. Strojové učení (walk-forward LightGBM)
- **Data:** 18 rysů známých při vstupu: hodina, den, ATR, výnosy, vzdálenost k high/low předchozího dne, noční rozsah, delta za 60 min, kumulativní delta session, trend, RSI2, režim volatility.
- **Postup:** trénink na všech letech před rokem Y, test na roce Y (2015–2026), obchod jen při p(výhry) > breakeven + 3 %.
- **AUC:**
  - intraday 0,59–0,82;
  - 5 dní 0,48–0,76.
  
  Model dobře poznává, kdy je trh dost volatilní na dosažení TP. Nepozná ale směr, takže zvýšená šance na TP jde ruku v ruce se zvýšenou šancí na SL.
- **Výsledky vybraných obchodů proti všem:**

| Horizont / směr | Lepší než „všechny obchody“ | Typické |
|---|---|---|
| intraday long | 5 z 7 kombinací s obchody | nestabilní: rok od roku −0,2 až +0,5 R; výběr se koncentruje do volatilních let (2022: 2 269 obchodů) |
| intraday short | 2 z 7 | horší |
| 5D long | 3 z 9 | většinou horší |
| 5D short | 1 z 9 | horší |

- **Nejlepší** (intraday long SL 20, RRR 1:3): +0,11 R na 962 obchodů. Je to ale 1 z 36 kombinací a lepší jen v 67 % let.

## Odpovědi na otázky
1. **Jsou strategie s vysokým RRR úspěšnější na menších timeframes?** Ne.
   - Intradenně jsou 1:10–1:25 v nule až ztrátě, protože TP skoro nikdy nedojde.
   - Na delších horizontech „fungují“ jen díky růstu indexu, a to stejně dobře jako 1:1,5.
2. **Vychází lépe menší RRR 1,5:1?** Ne lépe, ani hůř.
   - Win rate přesně odpovídá náhodě, rozdíl dělá jen horizont (drift) a náklady.
   - Výhoda nízkého RRR: kratší série ztrát (max 13–33 místo stovek), takže lepší psychologie i řízení rizika.
3. **SL podle ATR v hodině / dni / týdnu:** ano, nutné kvůli stacionaritě. Bez dobrého vstupu ale edge nevytvoří.
4. **Optimální hodiny, dny, týdny:**
   - drží jen hodina (večerní Globex, noční drift);
   - dny v týdnu a měsíce mimo vzorek nedrží.
5. **Alfa 3+ proti B&H:** nedosáhla ji žádná kombinace (t ≥ 2).
6. **Stop-hunt + kumulativní delta:** nepotvrzeno.
7. **Sondovací pozice:** zhoršuje. Průměrování dolů edge nepřidá a zvyšuje riziko.
8. **Může kód sám ukládat situace a obchody a učit se (ML)?** Ano, technicky to jde:
   - databáze všech situací a obchodů;
   - pravidelné přetrénování walk-forward;
   - online learning;
   - monitoring a kill kritérium.
   
   Data ale ukazují, že se model naučí hlavně volatilitu, ne směr. Zlepšení není stabilní mezi roky. ML zesílí edge, která existuje, ale nevytvoří ji.
9. **Lze parametry optimalizovat?** Optimalizace SL/RRR/okna na minulých datech mimo vzorek nefunguje: výběr měsíce −0,27 R, výběr top kombinací v předchozích studiích také.
   Robustní jsou jen:
   - SL v ATR (ne v bodech);
   - long bias;
   - horizont dny až týdny;
   - nízké náklady vůči SL;
   - velikost pozice podle volatility.
