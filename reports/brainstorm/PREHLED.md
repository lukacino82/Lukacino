# Brainstorming: hledání dalších systémů s hranou na ES (07/2016–07/2026)

Data: volume bary z Excelu (vč. bid/ask objemu = delta), rozhodnutí v 15:58 ET, náklady 0,5 b. na obchod. Skripty `analysis/brainstorm/`: `features.py` (denní tabulka), `hypotheses.py` (kola 1–5, `ROUND=1..5`), `exposure.py`, `portfolio.py`, `report.py`. Grafy: `equity_systemy.png`, `ucet.png`.

**Kritéria:** mechanismus předem, málo parametrů; **p** = jak často stejná pravidla v náhodné dny (bez podmínky) vyjdou stejně dobře (2 000×); **alfa t** = t úseku regrese denního P&L na denní pohyb ES; kladné v 2016–21 i 2022–26; sousední parametry kladné. Celkem ~70 variant, takže nejlepší t čistě náhodou ≈ √(2·ln 70) ≈ 2,9.


## Kolo 1: IBS, série poklesů, noc, intradenní momentum, gap fade, VWAP, panika, short v medvědím trhu, delta, stop-run, přelom měsíce

| Rodina | Varianta | Obchodů | b./obchod | t | p (náhoda) | alfa t | 2016–21 t | 2022–26 t |
|---|---|---|---|---|---|---|---|---|
| A IBS nízký close v rámci dne | IBS < 0.1 → long 1 den | 194 | 5,4 | 1,39 | 0,122 | 0,75 | 1,02 | 1,00 |
| A IBS nízký close v rámci dne | IBS < 0.2 → long 1 den | 345 | 5,1 | 1,64 | 0,060 | 0,77 | 1,62 | 0,97 |
| A IBS nízký close v rámci dne | IBS < 0.3 → long 1 den | 476 | 3,4 | 1,33 | 0,179 | 0,29 | 0,96 | 0,97 |
| B Série poklesů | 2 nižší close → long do 1. vyššího close (max 10) | 260 | 12,2 | 3,42 | 0,052 | 1,83 | 1,26 | 3,31 |
| B Série poklesů | 3 nižší close → long do 1. vyššího close (max 10) | 113 | 26,4 | 4,85 | 0,000 | 2,90 | 3,09 | 3,87 |
| B Série poklesů | 4 nižší close → long do 1. vyššího close (max 10) | 47 | 37,2 | 3,32 | 0,000 | 2,16 | −0,07 | 3,57 |
| C Noční držení | každou noc close → open | 1139 | 0,6 | 0,75 | 0,607 | −1,95 | 1,75 | −0,38 |
| C Noční držení | noc po poklesovém dni | 700 | 2,0 | 1,67 | 0,141 | −0,09 | 1,26 | 1,16 |
| C Noční držení | noc po IBS < 0,3 | 476 | 1,8 | 1,28 | 0,231 | 0,29 | 0,43 | 1,27 |
| C Noční držení | noc nad MA200 | 920 | 1,1 | 1,50 | 0,412 | 0,02 | 1,48 | 0,78 |
| D Intradenní momentum (Gao 2018) | směr 1. půlhodiny, 15:30–16:00 | 2265 | −1,0 | −4,01 | 0,483 | −4,06 | −4,24 | −1,71 |
| D Intradenní momentum (Gao 2018) | směr 1. půlhodiny, 15:30–16:00, |r1|>0,25 ATR | 1389 | −1,5 | −4,66 | 0,508 | −4,69 | −4,04 | −2,63 |
| D Intradenní momentum (Gao 2018) | směr 1. půlhodiny, 15:30–16:00, jen long | 1270 | −1,0 | −3,30 | 0,505 | −3,66 | −4,05 | −0,92 |
| E Gap fade s potvrzením | RRR 2, oba směry | 724 | 0,8 | 1,09 | 0,516 | 1,19 | −0,85 | 1,88 |
| E Gap fade s potvrzením | RRR 1, oba směry | 724 | 1,0 | 1,61 | 0,503 | 1,73 | 0,90 | 1,34 |
| E Gap fade s potvrzením | RRR 2, jen long | 319 | 1,0 | 0,83 | 0,513 | 0,60 | −0,20 | 1,06 |
| E Gap fade s potvrzením | RRR 2, jen short | 405 | 0,7 | 0,71 | 0,499 | 1,09 | −0,91 | 1,60 |
| F VWAP ±zσ reverze | z = 2, long pod VWAP | 1185 | −1,3 | −2,16 | 0,514 | −2,90 | −0,44 | −2,21 |
| F VWAP ±zσ reverze | z = 2.5, long pod VWAP | 780 | −1,3 | −1,69 | 0,526 | −2,25 | 0,13 | −1,94 |
| F VWAP ±zσ reverze | z = 2, short nad VWAP | 1246 | −1,1 | −2,38 | 0,501 | −1,94 | −1,74 | −1,73 |
| F VWAP ±zσ reverze | z = 2.5, short nad VWAP | 694 | −0,9 | −1,45 | 0,500 | −1,06 | −0,78 | −1,22 |
| G Panický den | rozpětí > 1.25 ATR a IBS < 0,25 → long do close > včerejší high (max 5) | 132 | 1,8 | 0,24 | 0,764 | −1,12 | 1,43 | −0,50 |
| G Panický den | rozpětí > 1.5 ATR a IBS < 0,25 → long do close > včerejší high (max 5) | 98 | 9,2 | 0,95 | 0,338 | −0,17 | 2,00 | 0,02 |
| G Panický den | rozpětí > 2 ATR a IBS < 0,25 → long do close > včerejší high (max 5) | 48 | 2,9 | 0,19 | 0,640 | −0,73 | 1,03 | −0,34 |
| H Short v medvědím režimu | pod MA200 a RSI(2) > 80 → short do close < MA5 (max 10) | 41 | 3,6 | 0,19 | 0,248 | 0,90 | 0,40 | 0,04 |
| H Short v medvědím režimu | pod MA200 a RSI(2) > 90 → short do close < MA5 (max 10) | 26 | −5,5 | −0,23 | 0,570 | 0,20 | 0,65 | −0,51 |
| H Short v medvědím režimu | pod MA200 a RSI(2) > 95 → short do close < MA5 (max 10) | 11 | – | – | – | – | – | – |
| I Delta divergence | pokles a RTH delta > 0 → long 1 den | 297 | −6,6 | −1,93 | 0,999 | −3,21 | −1,76 | −1,13 |
| I Delta divergence | pokles, delta > 0 a IBS < 0,3 → long 1 den | 117 | −4,5 | −0,61 | 0,919 | −1,52 | −1,52 | 0,01 |
| J Stop-run overnight extrému | pod overnight low a zpět v 10:00 → long do 16:00 | 272 | 1,0 | 0,52 | 0,500 | 0,09 | −0,45 | 0,90 |
| J Stop-run overnight extrému | nad overnight high a zpět v 10:00 → short do 16:00 | 330 | −2,4 | −1,10 | 0,512 | −0,49 | −0,89 | −0,79 |
| K Přelom měsíce | close 1. den před koncem měsíce → close 3. dne nového měsíce | 110 | 8,0 | 1,06 | 0,474 | 0,07 | 1,23 | 0,41 |
| K Přelom měsíce | close 2. den před koncem měsíce → close 3. dne nového měsíce | 110 | 13,9 | 1,62 | 0,323 | 0,58 | 1,44 | 0,96 |
| K Přelom měsíce | close 1. den před koncem měsíce → close 1. dne nového měsíce | 110 | 2,5 | 0,46 | 0,551 | −0,13 | 0,17 | 0,44 |

## Kolo 2: kalendář a toky (týdenní reverze, víkend, svátky, FOMC, opční expirace, N-denní low, reverze na konci dne)

| Rodina | Varianta | Obchodů | b./obchod | t | p (náhoda) | alfa t | 2016–21 t | 2022–26 t |
|---|---|---|---|---|---|---|---|---|
| L Týdenní reverze | týden dolů → long pátek close do dalšího pátku | 140 | 12,4 | 1,24 | 0,101 | 0,07 | 0,81 | 0,94 |
| L Týdenní reverze | týden dolů o víc než 1 ATR → long pátek close do dalšího pátku | 88 | 10,7 | 0,75 | 0,204 | −0,34 | 0,59 | 0,49 |
| M Víkend a pondělí | pátek close → pondělí close | 403 | 4,3 | 1,92 | 0,092 | 1,20 | 0,39 | 2,26 |
| M Víkend a pondělí | pondělí open → close | 477 | 2,1 | 1,46 | 0,110 | 0,94 | −0,15 | 1,90 |
| N Před svátkem | close 2 dny před svátkem → close den před svátkem | 88 | 7,3 | 2,31 | 0,105 | 2,01 | 1,50 | 1,77 |
| N Před svátkem | close den před svátkem → close po svátku | 88 | −8,5 | −1,85 | 0,977 | −2,23 | −0,56 | −1,83 |
| O Před FOMC (Lucca–Moench) | close den před FOMC → 13:58 v den FOMC | 72 | 6,1 | 1,95 | 0,171 | 1,72 | 0,90 | 1,79 |
| O Před FOMC (Lucca–Moench) | open → 13:58 v den FOMC | 72 | −1,0 | −0,65 | 0,631 | −0,77 | −0,77 | −0,15 |
| O Před FOMC (Lucca–Moench) | close den před FOMC → close v den FOMC | 72 | 0,9 | 0,15 | 0,538 | −0,23 | 0,45 | −0,06 |
| P Opční expirace | long týden expirace (pátek close před → close expirace) | 110 | −1,0 | −0,10 | 0,856 | −1,11 | −0,33 | 0,08 |
| P Opční expirace | short týden po expiraci (close expirace → další pátek) | 110 | −14,9 | −1,62 | 0,921 | −0,88 | −0,51 | −1,66 |
| Q N-denní low nad MA200 (Connors) | close = 5denní low a nad MA200 → long do close > MA5 (max 10) | 158 | 10,9 | 2,26 | 0,270 | 0,79 | 1,80 | 1,47 |
| Q N-denní low nad MA200 (Connors) | close = 10denní low a nad MA200 → long do close > MA5 (max 10) | 87 | 14,3 | 1,89 | 0,145 | 0,62 | 2,42 | 0,67 |
| R Reverze na konci dne (a posteriori!) | pohyb open→15:30 > 0,5 ATR → proti němu 15:30–16:00 | 918 | −0,4 | −1,09 | 0,506 | −1,23 | −1,27 | −0,38 |
| R Reverze na konci dne (a posteriori!) | proti směru 1. půlhodiny, |r1| > 0,25 ATR, 15:30–16:00 | 1389 | 0,5 | 1,54 | 0,518 | 1,58 | 1,56 | 0,66 |

## Kolo 3: order flow a objem (absorpce, kapitulace, rebalancing, reverzní den)

| Rodina | Varianta | Obchodů | b./obchod | t | p (náhoda) | alfa t | 2016–21 t | 2022–26 t |
|---|---|---|---|---|---|---|---|---|
| S Absorpce (pasivní strana vyhrává) | růst, ale delta < 0 (pasivní kupci) → long 1 den | 375 | −3,0 | −1,44 | 0,966 | −2,31 | −1,08 | −0,97 |
| S Absorpce (pasivní strana vyhrává) | pokles, ale delta > 0 (pasivní prodejci) → short 1 den | 297 | 5,6 | 1,64 | 0,002 | 2,88 | 1,51 | 0,95 |
| S Absorpce (pasivní strana vyhrává) | oba směry dohromady | 605 | 1,0 | 0,51 | 0,059 | 0,78 | 1,16 | −0,24 |
| S Absorpce (pasivní strana vyhrává) | silná verze: |delta| > medián 20 dní, oba směry | 283 | −6,6 | −1,92 | 0,950 | −1,52 | −1,10 | −1,59 |
| T Kapitulační objem | pokles a objem > 1.3× průměr 20 dní → long do close > včerejší high (max 5) | 153 | 7,7 | 1,26 | 0,384 | −0,01 | 1,62 | 0,48 |
| T Kapitulační objem | pokles a objem > 1.6× průměr 20 dní → long do close > včerejší high (max 5) | 65 | 27,1 | 2,68 | 0,004 | 1,34 | 2,09 | 1,72 |
| U Rebalancing na konci měsíce | 3 dny před koncem měsíce: MTD > +1.5 ATR → short, < −1.5 ATR → long, do konce měsíce | 88 | −2,8 | −0,38 | 0,580 | −0,48 | −0,62 | −0,03 |
| U Rebalancing na konci měsíce | 3 dny před koncem měsíce: MTD > +2.5 ATR → short, < −2.5 ATR → long, do konce měsíce | 70 | −1,2 | −0,15 | 0,486 | −0,30 | −0,45 | 0,14 |
| V Býčí reverzní den | gap dolů > 0,2 ATR a close > open → long 1 den | 309 | −3,6 | −1,25 | 0,968 | −2,26 | −0,11 | −1,39 |
| V Býčí reverzní den | nové 20denní low intradenně a close v horní polovině → long 1 den | 58 | −2,3 | −0,27 | 0,730 | −0,72 | −0,08 | −0,26 |

## Kolo 4: mimo seanci (znovuotevření Globexu, Evropa)

| Rodina | Varianta | Obchodů | b./obchod | t | p (náhoda) | alfa t | 2016–21 t | 2022–26 t |
|---|---|---|---|---|---|---|---|---|
| W Fade gapu po znovuotevření Globexu | gap > 0.1 ATR, jen neděle večer → proti gapu do zaplnění nebo 09:30 | 214 | −3,5 | −1,68 | 0,508 | −1,99 | −1,49 | −0,90 |
| W Fade gapu po znovuotevření Globexu | gap > 0.25 ATR, jen neděle večer → proti gapu do zaplnění nebo 09:30 | 81 | −3,7 | −0,78 | 0,506 | −1,03 | −0,56 | −0,55 |
| W Fade gapu po znovuotevření Globexu | gap > 0.1 ATR, každý den 18:00 → proti gapu do zaplnění nebo 09:30 | 218 | −4,1 | −1,95 | 0,519 | −2,26 | −1,65 | −1,13 |
| X Evropská seance | směr 16:00→03:00 po něm 03:00→09:30 | 2253 | −0,9 | −2,24 | 0,490 | −2,15 | −1,63 | −1,63 |
| X Evropská seance | směr 16:00→03:00 po něm 03:00→09:30, |pohyb| > 0.2 ATR | 1181 | −1,0 | −1,69 | 0,505 | −1,54 | −1,24 | −1,20 |
| X Evropská seance | směr 16:00→03:00 proti něm 03:00→09:30, |pohyb| > 0.2 ATR | 1181 | −0,0 | −0,00 | 0,501 | −0,16 | −0,35 | 0,25 |

## Kolo 5: robustnost kandidátů (základ)

| Rodina | Varianta | Obchodů | b./obchod | t | p (náhoda) | alfa t | 2016–21 t | 2022–26 t |
|---|---|---|---|---|---|---|---|---|
| 1 RSI(2) | RSI(2) < 10 nad MA200 → do close > MA5 (max 10) | 76 | 25,4 | 3,61 | 0,004 | 2,03 | 2,09 | 2,97 |
| 2 Série poklesů | 3 nižší close → do 1. vyššího close (max 10) | 113 | 26,4 | 4,85 | 0,000 | 2,90 | 3,09 | 3,87 |
| 2 Série poklesů | 3 nižší close → do close > MA5 (max 10) | 107 | 30,0 | 3,80 | 0,000 | 2,09 | 1,06 | 4,54 |
| 2 Série poklesů | 3 nižší close → do close > včerejší high (max 10) | 105 | 31,9 | 3,88 | 0,000 | 2,56 | 2,75 | 2,84 |
| 2 Série poklesů | 3 nižší close → do 1. vyššího close (max 5) | 113 | 26,4 | 4,85 | 0,000 | 2,90 | 3,09 | 3,87 |
| 2 Série poklesů | 3 nižší close → jen nad MA200, do 1. vyššího close (max 10) | 75 | 17,6 | 3,62 | 0,037 | 2,22 | 2,24 | 2,87 |
| 2 Série poklesů | 2 nižší close → do 1. vyššího close (max 10) | 260 | 12,2 | 3,42 | 0,059 | 1,83 | 1,26 | 3,31 |
| 2 Série poklesů | 4 nižší close → do 1. vyššího close (max 10) | 47 | 37,2 | 3,32 | 0,000 | 2,16 | −0,07 | 3,57 |
| 2 Série poklesů | 5 nižší close → do 1. vyššího close (max 10) | 12 | – | – | – | – | – | – |
| 3 Kapitulační objem | pokles a objem > 1.4× průměr 20 dní → do close > včerejší high (max 5) | 117 | 8,4 | 1,22 | 0,373 | −0,05 | 0,98 | 0,79 |
| 3 Kapitulační objem | pokles a objem > 1.6× průměr 20 dní → do close > včerejší high (max 5) | 65 | 27,1 | 2,68 | 0,004 | 1,34 | 2,09 | 1,72 |
| 3 Kapitulační objem | pokles a objem > 1.8× průměr 20 dní → do close > včerejší high (max 5) | 40 | 30,0 | 2,48 | 0,009 | 1,72 | 1,97 | 1,49 |
| 3 Kapitulační objem | pokles a objem > 2× průměr 20 dní → do close > včerejší high (max 5) | 24 | 22,4 | 1,49 | 0,108 | 0,75 | 1,98 | 0,10 |
| 3 Kapitulační objem | pokles a objem > 1,6× → do 1. vyššího close (max 5) | 75 | 16,1 | 2,18 | 0,067 | 0,97 | 1,11 | 1,92 |
| 4 Absorpce short | pokles a delta > 0 → short 1 den/dny | 297 | 5,6 | 1,64 | 0,001 | 2,88 | 1,51 | 0,95 |
| 4 Absorpce short | pokles a delta > 0 → short 2 den/dny | 267 | 3,3 | 0,72 | 0,029 | 2,38 | 0,64 | 0,44 |
| 4 Absorpce short | pokles a delta > 0 → short 3 den/dny | 243 | 6,8 | 1,37 | 0,004 | 3,22 | 0,99 | 0,96 |
| 4 Absorpce short | pokles a delta > 0, pod MA200 → short 1 den | 89 | 6,4 | 0,76 | 0,041 | 1,53 | 1,08 | 0,22 |
| 4 Absorpce short | pokles a delta > 0, nad MA200 → short 1 den | 210 | 5,3 | 1,60 | 0,011 | 2,34 | 1,05 | 1,20 |
| 5 Před svátkem | close 2 dny před svátkem → close den před svátkem | 88 | 7,3 | 2,31 | 0,119 | 2,01 | 1,50 | 1,77 |

## Kolo 5: dvojnásobné náklady 1 b.

| Rodina | Varianta | Obchodů | b./obchod | t | p (náhoda) | alfa t | 2016–21 t | 2022–26 t |
|---|---|---|---|---|---|---|---|---|
| 1 RSI(2) | RSI(2) < 10 nad MA200 → do close > MA5 (max 10) | 76 | 24,9 | 3,54 | 0,004 | 1,98 | 2,03 | 2,92 |
| 2 Série poklesů | 3 nižší close → do 1. vyššího close (max 10) | 113 | 25,9 | 4,76 | 0,000 | 2,85 | 3,00 | 3,81 |
| 2 Série poklesů | 3 nižší close → do close > MA5 (max 10) | 107 | 29,5 | 3,73 | 0,000 | 2,04 | 1,03 | 4,49 |
| 2 Série poklesů | 3 nižší close → do close > včerejší high (max 10) | 105 | 31,4 | 3,82 | 0,000 | 2,51 | 2,70 | 2,80 |
| 2 Série poklesů | 3 nižší close → do 1. vyššího close (max 5) | 113 | 25,9 | 4,76 | 0,000 | 2,85 | 3,00 | 3,81 |
| 2 Série poklesů | 3 nižší close → jen nad MA200, do 1. vyššího close (max 10) | 75 | 17,1 | 3,52 | 0,037 | 2,16 | 2,16 | 2,80 |
| 2 Série poklesů | 2 nižší close → do 1. vyššího close (max 10) | 260 | 11,7 | 3,28 | 0,059 | 1,71 | 1,15 | 3,22 |
| 2 Série poklesů | 4 nižší close → do 1. vyššího close (max 10) | 47 | 36,7 | 3,27 | 0,000 | 2,13 | −0,13 | 3,53 |
| 2 Série poklesů | 5 nižší close → do 1. vyššího close (max 10) | 12 | – | – | – | – | – | – |
| 3 Kapitulační objem | pokles a objem > 1.4× průměr 20 dní → do close > včerejší high (max 5) | 117 | 7,9 | 1,14 | 0,373 | −0,11 | 0,90 | 0,76 |
| 3 Kapitulační objem | pokles a objem > 1.6× průměr 20 dní → do close > včerejší high (max 5) | 65 | 26,6 | 2,63 | 0,004 | 1,30 | 2,04 | 1,70 |
| 3 Kapitulační objem | pokles a objem > 1.8× průměr 20 dní → do close > včerejší high (max 5) | 40 | 29,5 | 2,44 | 0,009 | 1,69 | 1,93 | 1,47 |
| 3 Kapitulační objem | pokles a objem > 2× průměr 20 dní → do close > včerejší high (max 5) | 24 | 21,9 | 1,45 | 0,108 | 0,73 | 1,94 | 0,09 |
| 3 Kapitulační objem | pokles a objem > 1,6× → do 1. vyššího close (max 5) | 75 | 15,6 | 2,11 | 0,067 | 0,92 | 1,02 | 1,89 |
| 4 Absorpce short | pokles a delta > 0 → short 1 den/dny | 297 | 5,1 | 1,49 | 0,001 | 2,72 | 1,39 | 0,85 |
| 4 Absorpce short | pokles a delta > 0 → short 2 den/dny | 267 | 2,8 | 0,62 | 0,029 | 2,26 | 0,55 | 0,37 |
| 4 Absorpce short | pokles a delta > 0 → short 3 den/dny | 243 | 6,3 | 1,27 | 0,004 | 3,10 | 0,91 | 0,89 |
| 4 Absorpce short | pokles a delta > 0, pod MA200 → short 1 den | 89 | 5,9 | 0,70 | 0,041 | 1,47 | 1,05 | 0,17 |
| 4 Absorpce short | pokles a delta > 0, nad MA200 → short 1 den | 210 | 4,8 | 1,45 | 0,011 | 2,18 | 0,91 | 1,12 |
| 5 Před svátkem | close 2 dny před svátkem → close den před svátkem | 88 | 6,8 | 2,15 | 0,119 | 1,87 | 1,36 | 1,67 |

## Kolo 5: rozhodnutí 16:00

| Rodina | Varianta | Obchodů | b./obchod | t | p (náhoda) | alfa t | 2016–21 t | 2022–26 t |
|---|---|---|---|---|---|---|---|---|
| 1 RSI(2) | RSI(2) < 10 nad MA200 → do close > MA5 (max 10) | 79 | 24,6 | 3,59 | 0,004 | 1,94 | 1,45 | 3,51 |
| 2 Série poklesů | 3 nižší close → do 1. vyššího close (max 10) | 113 | 20,1 | 3,39 | 0,003 | 1,99 | 0,95 | 3,45 |
| 2 Série poklesů | 3 nižší close → do close > MA5 (max 10) | 110 | 27,1 | 3,36 | 0,001 | 1,81 | 0,49 | 4,70 |
| 2 Série poklesů | 3 nižší close → do close > včerejší high (max 10) | 107 | 24,4 | 2,86 | 0,003 | 1,71 | 1,45 | 2,47 |
| 2 Série poklesů | 3 nižší close → do 1. vyššího close (max 5) | 113 | 20,1 | 3,39 | 0,002 | 1,99 | 0,95 | 3,45 |
| 2 Série poklesů | 3 nižší close → jen nad MA200, do 1. vyššího close (max 10) | 77 | 11,0 | 2,03 | 0,194 | 1,15 | 0,79 | 2,09 |
| 2 Série poklesů | 2 nižší close → do 1. vyššího close (max 10) | 260 | 9,7 | 2,54 | 0,138 | 1,15 | 0,87 | 2,50 |
| 2 Série poklesů | 4 nižší close → do 1. vyššího close (max 10) | 51 | 26,7 | 2,34 | 0,002 | 1,46 | −1,01 | 3,08 |
| 2 Série poklesů | 5 nižší close → do 1. vyššího close (max 10) | 20 | 18,1 | 1,67 | 0,143 | 0,71 | −0,49 | 2,72 |
| 3 Kapitulační objem | pokles a objem > 1.4× průměr 20 dní → do close > včerejší high (max 5) | 119 | 8,7 | 1,30 | 0,324 | 0,04 | 0,65 | 1,13 |
| 3 Kapitulační objem | pokles a objem > 1.6× průměr 20 dní → do close > včerejší high (max 5) | 64 | 24,5 | 2,43 | 0,011 | 1,11 | 1,60 | 1,85 |
| 3 Kapitulační objem | pokles a objem > 1.8× průměr 20 dní → do close > včerejší high (max 5) | 40 | 28,4 | 2,28 | 0,012 | 1,57 | 1,74 | 1,46 |
| 3 Kapitulační objem | pokles a objem > 2× průměr 20 dní → do close > včerejší high (max 5) | 24 | 21,4 | 1,37 | 0,127 | 0,71 | 1,86 | 0,11 |
| 3 Kapitulační objem | pokles a objem > 1,6× → do 1. vyššího close (max 5) | 74 | 14,7 | 1,92 | 0,074 | 0,79 | 0,49 | 2,03 |
| 4 Absorpce short | pokles a delta > 0 → short 1 den/dny | 307 | 6,2 | 1,90 | 0,000 | 3,16 | 1,43 | 1,31 |
| 4 Absorpce short | pokles a delta > 0 → short 2 den/dny | 277 | 4,5 | 1,00 | 0,011 | 2,71 | 0,57 | 0,82 |
| 4 Absorpce short | pokles a delta > 0 → short 3 den/dny | 248 | 9,6 | 1,96 | 0,000 | 3,87 | 1,42 | 1,37 |
| 4 Absorpce short | pokles a delta > 0, pod MA200 → short 1 den | 91 | 9,1 | 1,13 | 0,011 | 1,90 | 0,90 | 0,75 |
| 4 Absorpce short | pokles a delta > 0, nad MA200 → short 1 den | 217 | 5,2 | 1,61 | 0,011 | 2,36 | 1,12 | 1,18 |
| 5 Před svátkem | close 2 dny před svátkem → close den před svátkem | 88 | 6,5 | 2,09 | 0,139 | 1,82 | 1,28 | 1,65 |

## Řízení expozice (volatility timing, MA200)

| Varianta | Sharpe | Max DD (b.) | alfa t | beta |
|---|---|---|---|---|
| Buy & hold 1 ES | 0,66 | −1216 | 1,32 | 1,00 |
| Volatility timing (σ 20 dní, strop 2×, průměrná expozice 1×) | 0,70 | −748 | 0,75 | 0,65 |
| Volatility timing σ 20 dní, zaokrouhleno na celé ES | 0,38 | −1351 | −0,57 | 0,66 |
| Volatility timing (σ 60 dní, strop 2×, průměrná expozice 1×) | 0,64 | −937 | 0,27 | 0,70 |
| Volatility timing σ 60 dní, zaokrouhleno na celé ES | 0,42 | −1362 | −0,77 | 0,78 |
| Trend: long jen nad MA200 | 0,67 | −810 | 0,88 | 0,51 |
| Volatility timing σ20 × trend MA200 | 0,59 | −731 | 0,63 | 0,43 |

## Portfolio kandidátů (každý systém 1 ES, 05/2017–07/2026)

| Systém | Zisk | Sharpe | Max DD (b.) | alfa (b./rok) | alfa t | beta | Sharpe 16–21 / 22–26 | V trhu |
|---|---|---|---|---|---|---|---|---|
| RSI(2) < 10 nad MA200 | $97k | 0,86 | −388 | 157 | 2,03 | 0,12 | 0,68 / 1,02 | 11 % |
| 3 nižší close | $149k | 1,15 | −374 | 254 | 2,90 | 0,16 | 1,13 / 1,26 | 8 % |
| VAL swing | $147k | 0,60 | −1136 | 66 | 0,55 | 0,54 | 1,11 / 0,36 | 45 % |
| Kapitulační objem 1,6× | $88k | 0,67 | −316 | 118 | 1,34 | 0,16 | 0,87 / 0,55 | 9 % |
| Absorpce short | $83k | 0,54 | −458 | 286 | 2,88 | −0,22 | 0,70 / 0,45 | 13 % |
| Portfolio (všech 5) | $564k | 1,25 | −1228 | 882 | 3,20 | 0,75 | 1,49 / 1,13 | – % |
| Portfolio bez VAL | $417k | 1,39 | −840 | 816 | 3,83 | 0,21 | 1,35 / 1,45 | – % |
| Buy & hold 1 ES | $217k | 0,66 | −1216 | 0 | 1,32 | 1,00 | 0,92 / 0,50 | 100 % |

**Korelace denního P&L:**

| | RSI(2) < 10 nad MA200 | 3 nižší close | VAL swing | Kapitulační objem 1,6× | Absorpce short |
|---|---|---|---|---|---|
| RSI(2) < 10 nad MA200 | 1,00 | 0,34 | 0,39 | 0,51 | −0,19 |
| 3 nižší close | 0,34 | 1,00 | 0,46 | 0,54 | −0,27 |
| VAL swing | 0,39 | 0,46 | 1,00 | 0,47 | −0,33 |
| Kapitulační objem 1,6× | 0,51 | 0,54 | 0,47 | 1,00 | −0,17 |
| Absorpce short | −0,19 | −0,27 | −0,33 | −0,17 | 1,00 |

## Simulace účtu $50 000 v MES (reinvestice, páka na systém)

| Plán | Konec | CAGR | Max DD |
|---|---|---|---|
| Konzervativní: 5 systémů, páka 0,5× na systém | $106,364 | 8,6 % | −8 % |
| Střední: 5 systémů, páka 1× na systém | $351,199 | 23,6 % | −20 % |
| Agresivní: 5 systémů, páka 2× na systém, brzdy −20 %/−30 % | $2,038,361 | 49,7 % | −40 % |
| Buy & hold 1× | $118,632 | 9,9 % | −28 % |

## Závěr

| Systém | Hodnocení | Proč |
|---|---|---|
| RSI(2) < 10 nad MA200 | **silný** | pravidla z literatury (2008), p 0,004, t 3,6, obě období, robustní na čas i náklady |
| 3 nižší close → do 1. vyššího close | **silný (nový)** | t 4,85 nad prahem 2,9, p < 0,001, alfa t 2,9, obě období, 3 různé výstupy t 3,8–4,9, rozhodnutí 16:00 t 3,4; 56 % obchodů mimo pozice RSI(2) má t 4,2 |
| Absorpce short (pokles + delta > 0 → short 1 den) | **zkušební** | p ≤ 0,01 ve všech variantách, alfa t 2,4–3,9, záporná korelace s ostatními (−0,2 až −0,3); ale nalezeno a posteriori (otočení výsledku z kola 1) a t na obchod jen 1,5–2 |
| Kapitulační objem 1,6–1,8× | **zkušební** | p 0,004–0,012, obě období kladná, ale 1,4× a 2× slabé (úzké plató), alfa t 1,3 pod prahem |
| VAL swing | **slabý** | alfa t 0,55, beta 0,54 = hlavně expozice trhu; p 0,21 proti náhodě |
| Ostatní (~55 variant) | zamítnuto | intradenní momentum, VWAP reverze, gap fade, noc, FOMC, expirace, svátky, víkend, Globex, Evropa, rebalancing, panika, delta long |

Portfolio RSI(2) + 3 poklesy + absorpce + kapitulace (bez VAL): Sharpe 1,39 proti 0,66 u buy & hold, alfa t 3,8, beta 0,21. Tři z těchto systémů byly vybrány z ~70 variant na stejných datech, takže skutečný budoucí výsledek bude nižší. Nutný forward test.
