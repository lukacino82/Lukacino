# Livermore na ES 2009–2026 (23. 10. 2026)

Kód: `livermore/livermore.py`, výsledky `livermore/out/*.csv`.

## Principy převedené na pravidla (stanovená předem)
Zdroje: *How to Trade in Stocks* (1940), *Reminiscences of a Stock Operator* (1923, Project Gutenberg #60979).

| Princip | Pravidlo v testu |
|---|---|
| Pivotal point | Vstup long jen při průrazu: nové 20 / 55 / 252denní maximum close |
| Pyramidování | Sonda 20 %, +20 % při +1 ATR, +20 % při +2 ATR, +40 % při +3 ATR. Přidává se jen do zisku, nikdy se neprůměruje dolů |
| Cut losses | Počáteční stop 2 ATR, varianta 10 % (Livermorova max. ztráta) |
| „Když se nechová správně, ven“ | Časový stop: po 10 dnech není v zisku → výstup |
| Sit tight | Výstup jen při „přirozené reakci“: close o 3 nebo 6 ATR pod maximem, varianta pod 20denním low |
| Market Key | Zigzag pivoty s prahem 2/3/4 ATR. Long nad posledním pivotem high + ½ prahu, flat (nebo short) pod pivotem low − ½ prahu |

**Exekuce:** na open dalšího dne, náklad 0,5 b. na kontrakt.

**Srovnání:**
- tatáž pravidla bez pyramidy;
- náhodné vstupy se stejnou pyramidou a výstupy (200×);
- buy & hold.

## Výsledky (2009–2026, 42 variant)
| Systém | Expozice | CAGR | Sharpe | Max DD | Alfa/rok | Alfa t |
|---|---|---|---|---|---|---|
| Buy & hold ES | 100 % | 9,4 % | 0,74 | −28 % | – | – |
| Nejlepší: průraz 20D, plná pozice, výstup reakce 6 ATR | 83 % | 7,6 % | 0,80 | −14 % | +2,5 % | 1,58 |
| Totéž s pyramidou | 74 % | 5,5 % | 0,66 | −18 % | +1,3 % | 0,88 |
| Průraz 55D, pyramida, reakce 3 ATR | 29 % | 0,9 % | 0,23 | −12 % | −0,3 % | −0,32 |
| Průraz 252D (nová roční maxima), pyramida, 20denní low | 22 % | −0,3 % | −0,05 | −11 % | −1,2 % | −1,37 |
| Market Key 3 ATR, long/flat | 78 % | 5,9 % | 0,65 | −20 % | +1,2 % | 0,75 |
| Market Key 3 ATR, long/short | 98 % | 1,6 % | 0,18 | −29 % | +2,4 % | 0,75 |

## Hlavní zjištění
1. **Žádná varianta nemá prokazatelnou alfu.** Nejlepší t-statistika je 1,58, laťka je 2 (u 42 variant spíš 3). Nejlepší Sharpe 0,80 je jen o kousek nad B&H (0,74), CAGR je nižší (7,6 vs 9,4 %).
2. **Pyramidování na ES škodí.** Ve všech srovnatelných dvojicích má verze s pyramidou nižší CAGR, Sharpe i alfu než plná pozice hned při vstupu. Důvod: ES na horizontu dnů až týdnů spíš vrací (Swing Alpha). Přikupování po růstu o 1–3 ATR kupuje draho a následná reakce vyhodí celou pozici.
3. **Náhodné vstupy se stejnou pyramidou a výstupy dopadly lépe** než Livermorův průraz 55D. Průměrný Sharpe náhodných vstupů byl 0,42, průraz měl 0,23 (p = 0,92). Samotný „pivotal point“ tedy na ES informaci nenese.
4. **Profil výsledků přesně odpovídá Livermorovi:**
   - win rate 40–58 %;
   - průměrný zisk 2–11× větší než průměrná ztráta;
   - 35–56 % celého zisku přináší 10 % nejlepších obchodů.
   „Velké peníze se dělají sezením“ platí, jen to na ES nepřekoná prosté držení.
5. **Nová roční maxima (252D)** jsou nejhorší vstup (alfa t −0,8 až −1,4). To potvrzuje Edge Factory: po novém 52týdenním maximu ES roste pomaleji.
6. **Market Key long/short** ztrácí na shortech (drift ES). Long/flat jen kopíruje B&H s menší expozicí.

## Proč Livermorovi fungoval a nám ne
- **Jiný trh.** Obchodoval desítky akcií a komodit v letech 1900–1930, v méně efektivních trzích s pomalým šířením informací a silnými trendy.
- **Diverzifikace přes trhy.** Trendový princip dnes prokazatelně funguje jen jako trend-following přes desítky trhů (time-series momentum, CTA). Na jediném indexu ES je slabý.
- **Jeho vlastní výsledky měly obrovský rozptyl.** Několikrát zbankrotoval (mj. 1934) a jeho slavné výhry (1907, 1929) jsou malý vzorek.
- **Ověřitelná systematická pravidla nikdy nezveřejnil.** Jeho principy jsou diskreční; „pivotal point“ a „Market Key“ jsou interpretace.

## Co z Livermora použít
- **Řízení rizika a psychologie platí:** malá sonda, nepřidávat do ztráty, rychle řezat ztráty, nechat zisky běžet.
- **Trendovou logiku nepoužívat na samotném ES.** Má smysl až v portfoliu více trhů (NQ, ZN, CL, GC, měny), tedy trend-following CTA, k čemuž potřebujeme další data.

---

# One-Day Reversal (Livermore) na ES 2009–2026

Kód: `livermore/reversal.py`, výsledky `out/reversal_events.csv` a `out/reversal_system_years.csv`.

## Pravidla (podle zadání)
| Signál | Podmínky | Obchod |
|---|---|---|
| Býčí reverz | close > předchozí close, low < předchozí low, objem > předchozí objem | long |
| Medvědí reverz (jak je v zadání) | close < předchozí close, low > předchozí low, objem > předchozí objem | short |
| Medvědí reverz (klasický key reversal) | close < předchozí close, high > předchozí high, objem > předchozí objem | short |

**Varianty:** bez podmínky objemu; „po pohybu“ (býčí: low je 20denní minimum, medvědí: high je 20denní maximum).

**Měření:** vstup na open dalšího dne, výstup na close po 1, 2, 3, 5 a 10 dnech, v ATR, po nákladech.

**Excess:** výsledek minus průměrný den téhož roku na stejné straně, tím se odečte drift ES. Bere se jen nepřekrývající se signály.

## Výsledky
- Excess je nevýznamný ve všech 35 kombinacích (7 signálů × 5 horizontů). Nejvyšší |t| je 1,5, laťka je 2. Znaménko se mezi obdobími 2009–17, 2018–21 a 2022–26 mění.
- **Býčí reverz na 10 dní** vypadá dobře (+0,41 ATR, t 2,6, win 63 %). Je to ale jen drift ES: excess proti průměrnému dni je +0,05 ATR (t 0,3).
- **Medvědí reverzy** prodělávají (t −2 až −3), protože shortují proti driftu. Proti průměrnému dni jsou kolem nuly.
- **Varianta „po pohybu“** (reverz z 20denního low/high): málo signálů (37–149) a bez konzistence.
- **Podmínka vyššího objemu** nic nepřidává. Varianty bez objemu dopadly stejně nebo lépe.
- **Jednoduchý systém** (býčí reverz, long na 5 dní, stop 1 ATR): CAGR 0,5 %, t 0,53, v trhu 18 % dní. B&H 9,4 %.

## Závěr
One-day reversal na ES samostatně edge nemá. Podobně jako jiné svíčkové vzory (Edge Factory: 3 157 hypotéz) se chová jako šum. Livermore ho používal jako upozornění v kontextu (vyvrcholení dlouhého trendu u konkrétní akcie), ne jako mechanický vstup.

---

# Hypotézy ze tří knih ve složce na Drive (H1–H13)

Kód: `livermore/books_hypotheses.py`. Výsledky: `out/books_events.csv`, `out/books_round_numbers.csv`, `out/books_systems.csv` a `out/books_market_key_pct.csv`.

**Zdroje** (všechny přečteny celé):
- Livermore, *How to Trade in Stocks* (1940, HTTIS). Tabulky Market Key v příloze jsou nečitelné skeny, pravidla jsou ale popsaná v textu kapitol 8–9.
- Wyckoff, *Jesse Livermore's Methods of Trading in Stocks* (WY).
- Trade Navigator, manuál *Livermore Lines* (LL).

**Převod na ES:** Livermorovy bodové prahy platí pro akcie za 30–100 USD (6 bodů ≈ 6–20 %). Na ES jsou přepočtené na ATR(14) předchozího dne (≈ 1,3 % ceny), u Market Key na %.

**Měření:**
- Vstup na open dalšího dne, výstup na close po 5/10/20/60 dnech, výsledek v ATR.
- Excess = výsledek minus průměrný den téhož roku. Tím se odečte drift ES.
- Bere se jen nepřekrývající se signály. Období 2009–17, 2018–21 a 2022–26.

## Výsledky event study (long po signálu)
Excess je v ATR. Pro exit signály H5 a H10 Livermore předpovídá záporný excess.

| Hypotéza (zdroj) | n (h=20) | excess 5 d | excess 20 d | excess 60 d | max \|t\| | Verdikt |
|---|---|---|---|---|---|---|
| H1 průraz z konsolidace, 20D rozsah ≤ 3 ATR (HTTIS 1, 5) | 13 | −0,22 | −0,88 | −0,51 | 0,9 | ne – na ES vzácné a záporné |
| H2 první close nad novou stovkou / padesátkou (HTTIS 5) | 28–69 | −0,17 % | −0,29 % | – | **−2,4** | **opak** – po kulatém čísle horší než průměrný den |
| H3 nové maximum po normální reakci ≥ 1,5 ATR (HTTIS 1) | 103 | +0,03 | −0,24 | −0,65 | 0,8 | ne |
| H4 kontrola: nákup v reakci (Livermore: „nikdy“) | 100 | +0,12 | +0,14 | −0,15 | 0,7 | stejné nebo lepší než H3 |
| H5 abnormální reakce po růstu → slabost (HTTIS 2) | 11 | +0,92 | −0,72 | +0,08 | 1,4 | ne – n malé, znaménko opačné |
| H6 reakce na nízkém objemu (HTTIS 2) | 102 | −0,11 | −0,21 | −0,51 | 1,4 | ne – vysoký objem dopadl lépe |
| H7 test pivotu, dvojité dno (HTTIS 5) | 17 | −0,17 | +0,24 | +0,85 | 0,9 | ne |
| H8 po poklesu 20D ≥ 3 ATR (HTTIS: „nekupuj kvůli poklesu“) | 51 | 0,00 | +0,97 | +1,20 | 1,7 | **opak** – nákup po poklesu vydělává |
| H8 po poklesu 20D ≥ 5 ATR | 18 | +0,78 | +0,65 | +2,29 | 2,1 | opak, ale n = 16–25 |
| H9 panika: pokles ≥ 5 ATR a objem ≥ 1,5× (WY 8) | 7 | +1,27 | +0,28 | +2,65 | 1,6 | směr ano, n = 7 |
| H10 překoupenost ≥ 20D průměr + 2,5 ATR → prodat (WY 4) | 78 | −0,01 | 0,00 | −0,31 | 0,6 | ne |
| Referenční: nové 20D maximum bez podmínek | 144 | −0,09 | −0,16 | −0,38 | 1,1 | – |

**H8 a H9 nejsou nový objev.** Potvrzují dříve zjištěný mean-reversion profil ES: po velkém poklesu je nadprůměrný výnos. H8 ≥ 5 ATR na 60 dní má t 2,1, ale:
- je to jedna z 52 kombinací;
- n je 16;
- v letech 2018–21 je záporná (−1,4 ATR).
Livermorovo pravidlo „nekupuj kvůli poklesu“ na indexu ES neplatí. Pro jednotlivé akcie platit může (riziko bankrotu, žádný index rebalancing).

## H11 – Wyckoffovy výstupy (stop 1 ATR, cíl 3 ATR, max 10 dní) vs držení 20 dní
| Vstup | Výstup | Obchodů | R/obchod v ATR | t | Win | V trhu | CAGR | Alfa t |
|---|---|---|---|---|---|---|---|---|
| H3 nové max. po reakci | Wyckoff | 138 | +0,36 | 2,9 | 51 % | 22 % | 1,4 % | 0,79 |
| H3 nové max. po reakci | 20 dní | 100 | +0,77 | 2,5 | 73 % | 43 % | 3,0 % | 0,50 |
| H7 test pivotu | 20 dní | 17 | +1,04 | 1,8 | 71 % | 7 % | 1,2 % | −0,09 |
| Referenční 20D max. | Wyckoff | 236 | +0,29 | 2,9 | 47 % | 34 % | 2,6 % | 0,91 |
| Referenční 20D max. | 20 dní | 135 | +0,92 | 3,4 | 73 % | 58 % | 5,7 % | 1,28 |
| Buy & hold ES | – | – | – | – | – | 100 % | 9,4 % | – |

**Kladné R/obchod je jen drift ES.** Alfa proti ES je u všech nevýznamná (t ≤ 1,3). Livermorovské filtry (H3, H7) dopadly hůř než prosté nové 20denní maximum. Wyckoffův poměr cíl/stop 3:1 s časovým stopem drží zisk na obchod nízko a nepřidává nic.

## H13 – Market Key s procentními prahy (long/flat)
| Práh | V trhu | CAGR | Sharpe | maxDD | Alfa t |
|---|---|---|---|---|---|
| 5 % | 88 % | 6,5 % | 0,61 | −26 % | −0,10 |
| 8 % | 79 % | 5,0 % | 0,49 | −36 % | −1,13 |
| 10 % | 97 % | 9,0 % | 0,73 | −28 % | 0,23 |
| Buy & hold | 100 % | 9,4 % | 0,74 | −28 % | – |

Varianta 10 % je prakticky buy & hold. Nižší prahy jsou horší.

## Netestovatelné na samotném ES
- **Livermore Lines a Livermore** (trh → odvětví → tandem dvou akcií, HTTIS 3–4), **Key Price** ze dvou akcií téhož odvětví (HTTIS 8) a **vůdci odvětví** (WY): vyžadují desítky akcií a odvětvové indexy.
- **Divergence žito/pšenice** (HTTIS 3): vyžaduje dvě příbuzné komodity.
- **H12 pyramidování** (HTTIS 6, WY 6): otestováno dříve v `livermore.py`. Na ES je ve všech dvojicích horší než plná pozice.
- **Psychologická pravidla** (trpělivost, nepůjčovat, nebrat tipy, vybírat zisk z účtu): neměřitelná.

## Závěr
Ze 13 hypotéz žádná nemá na ES prokazatelnou edge ve směru, jak ji knihy formulují.
- Jediné dva významnější výsledky jdou **proti** Livermorovi:
  - kulatá čísla jsou spíš horší (t −2,4);
  - nákup po velkém poklesu vydělává (t až 2,1), což je známý mean-reversion indexu.
- Livermorovy principy byly psané pro jednotlivé akcie 20.–30. let, s jejich trendovostí, manipulací a rozdílnými vůdci odvětví. Na indexovém futures s driftem a mean-reversion po poklesech nefungují jako mechanický systém.
- Použitelné zůstává řízení rizika: rychlé omezení ztrát, nepřikupovat do ztráty, velikost pozice.
