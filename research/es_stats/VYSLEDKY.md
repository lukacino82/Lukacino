# Testy z poznámek: statistiky ES, kumulativní delta, VWAP, volume profile, money management, formace

**Data:**
- ES 1min back-adjusted, 2010/2011 – 9/2026. Bid/ask objem (kumulativní delta) je k dispozici od roku 2011.
- Procentní statistiky jsou z rekonstruované cash řady S&P 500.

**Kód a tabulky:**

| Blok | Složka |
|---|---|
| 1 Statistiky | `es_stats/` |
| 2–4 Delta, VWAP, profil | `delta_vwap/` |
| 5 Money management | `money_mgmt/` |
| 6 Formace a obraty | `patterns/` |

Grafy jsou v `es_stats/out/charts/`.

**Metodika:**
- U událostí měříme pohyb v ATR proti průměrnému pohybu ze stejné minuty dne ve stejném roce. To odstraní drift i denní sezónnost.
- t-statistika je klastrovaná po dnech.
- Obchody: TP/SL podle prvního dotyku, náklad 0,5 b. na obchod.
- Výběr na 2011–18, test na 2019–26.

## 1. Statistiky (`es_stats/out/`)

**Hodiny (A1, A2, A5):**
- Nejaktivnější hodiny (průměrné rozpětí % ceny):
  - 10:00–11:00 ET: 0,49 %
  - 9:30–10:00: 0,45 %
  - 15:00–16:00: 0,44 %
  - 11:00: 0,39 %
  - Mimo RTH: 3:00 ET (otevření Evropy) 0,27 % a 8:00 (data v 8:30) 0,31 %.
  - Nejklidnější jsou 23:00–1:00 (0,13 %).
- Nejaktivnější hodina podle dne v týdnu:

  | Den | Nejaktivnější hodina | Rozpětí |
  |---|---|---|
  | Po | 9:00 | 0,44 % (pondělí je celkově nejklidnější) |
  | Út | 10:00 | 0,49 % |
  | St | 15:00 a 14:00 | 0,48 % a 0,45 % (FOMC ve 14:00) |
  | Čt | 10:00 | 0,52 % |
  | Pá | 10:00 | 0,52 % |

- **Směr (long vs short):** pohyb nahoru a dolů v rámci hodiny je skoro stejný. Například 10:00 v pátek +7,9 b. nahoru vs −8,7 b. dolů.
  - Průměrný výnos žádné hodiny se neliší od ostatních.
  - Výjimkou je 2:00 ET (+0,010 % vs +0,002 %, t 3,5), což je známé okno 02–03 ET. To od roku 2021 nefunguje a na 1 ES nikdy nepokrylo náklady.

**Dny v týdnu (B1–B4):**

| Den | Výnos dne | P(růst) | Výprodeje (nejhorších 10 % dnů roku) | Pokles pod −2 % | Rozpětí RTH |
|---|---|---|---|---|---|
| Po | +0,054 % | 56,6 % | 8,8 % | 3,1 % | **0,96 %** |
| Út | +0,075 % | 53,8 % | 9,7 % | 2,0 % | 1,07 % |
| St | +0,072 % | 55,4 % | 9,6 % | 3,4 % | 1,13 % |
| Čt | +0,023 % | 53,5 % | 11,2 % | 4,0 % | 1,14 % |
| Pá | +0,027 % | 56,5 % | 11,2 % | 4,0 % | 1,08 % |

- **Výnos ani podíl výprodejů se mezi dny statisticky neliší** (p 0,15–0,91).
- **„Nejlepší den roku“ nebyl ani jednou za 16 let nejlepší i v následujícím roce** (při náhodě by to bylo 20 %). Tabulka nejlepších a nejhorších dnů po letech je v B3 a mění se náhodně.
- **Jediný robustní rozdíl je, že pondělí je nejklidnější:** rozpětí 0,96 % vs 1,11 % (t −4,8) a nejvyšší podíl choppy dnů (20 % vs 14–16 %). Ve čtvrtek je rozpětí největší (t +2,7).

**Propady (C, D1–D3):**
- **Roky:** výnos a max propad uvnitř roku.
  - 2013: +28 % / −7,9 %
  - 2017: +18,8 % / −3,5 %
  - 2020: +15,6 % / −35,2 %
  - 2022: −19,6 % / −27,6 %
  - 2025: +16,5 % / −22 %
  - Poměr výnos/propad: 5,4 (2017), 4,4 (2021), 3,6 (2013); záporný v roce 2018 (−0,30), 2022 (−0,71) a 2015 (−0,06). Celé řady jsou v `C_roky.csv`, `C_mesice.csv` a `C_tydny.csv`.
- **Průměrný největší propad uvnitř týdne podle roku:**

  | Rok | Průměr |
  |---|---|
  | 2017 | −1,0 % |
  | 2013–14 | −1,6 % |
  | 2019–21, 2023–24 | −1,9 až −2,1 % |
  | 2010–11 | −2,9 až −3,4 % |
  | 2022 | −4,0 % |
  | 2020 | −4,2 % |

  Nejhorší týden: −18,8 % (2020), −12,1 % (2010), −11,9 % (2025).
- **Průměrný největší propad uvnitř měsíce:** −1,9 % (2017) až −9,7 % (2022). Nejhorší měsíc: −30,1 % (březen 2020).
- **Kolik propadů „přežije“ účet** (D3):

  | Propad menší než | Týdnů | Měsíců | Roků |
  |---|---|---|---|
  | 5 % | 92,7 % | 65 % | – |
  | 10 % | 99,3 % | 90,6 % | 29 % |
  | 15 % | 99,7 % | 97,5 % | – |
  | 20 % | – | – | 71 % |
  | 30 % | – | – | 94 % |

- **Důsledek pro velikost pozice:** propady se nevyrovnávají po týdnech, ale skládají se do měsíců a let (−35 % v roce 2020, −27,6 % v roce 2022).
  - Při páce 2× znamenal rok 2020 −60 % účtu, při 3× −77 %.
  - Pokud má účet přežít propad −35 % se ztrátou nejvýš 50 %, nesmí celková expozice v nejhorším okamžiku přesáhnout ~1,4×.
  - Dokupování longů do poklesu tak zvyšuje páku přesně v nejhorším okamžiku (viz blok 5).

## 2. Kumulativní delta (`delta_vwap/out/A–C`)

- **Longy jen ve dnech s CD > 0** (v 10:00–15:00, CD od 9:30 nebo od 18:00): rozdíl k závěru dne je +0,003 až +0,013 ATR (≈ 0,1–0,5 b.), t 0,3–1,5. Longy při CD < 0 jsou o tolik horší. Nevýznamné, deset- až stokrát menší než náklady.
- **Extrémní delta** (první dosažení ±5k … ±40k kontraktů, nebo 0,5–3 % objemu dne):
  - Nikde t ≥ 2 do závěru dne. Pokračování ve směru delty je −0,016 až +0,024 ATR.
  - +30k kontraktů: +0,016 ATR za 60 min (t 2,0), do závěru dne t 1,2. Je to jediná hranice z 22 testovaných.
  - Záporné extrémy nedávají obrat (−20k: +0,010 ATR, t 0,6).
- **Flushing** (delta ≥ T, návrat k ~0, pak znovu ≥ 50 % původní hodnoty ve stejném směru):
  - 24 variant, jen 1 s |t| > 2 (T 5k short, 60 min −0,030 ATR, tedy obrat, ne pokračování).
  - Při 24 testech je to náhoda. Pokračování po flushi se nepotvrdilo.

## 3. VWAP (`delta_vwap/out/D–G`)

- **Fade ±1 / 2 / 3 SD** denního VWAP (od 18:00) i RTH VWAP (od 9:30): 120 variant.
  - Úspěšnost uzavřených obchodů je v průměru o 3,6 p. b. **pod** náhodnou hodnotou SL/(TP+SL).
  - Po nákladech jsou kladné 2 ze 120 variant, žádná s t > 2.
  - +2SD short → VWAP: 31,6 % vs náhodných 34,2 %. −2SD long → VWAP: 35,5 % vs 34,4 %.
- **Fade v balanci je horší, ne lepší.** Při plochém VWAP (|posun za 60 min| < 0,25 SD) má +2SD short 30,3 % vs 34,0 % a čistě −0,90 b./obchod. V trendovém dni −0,37 b.
- **Retest VWAPu po překročení** (průraz, ≥ 15/30 min na druhé straně, návrat k VWAP do 120 min): úspěšnost = náhoda (32–35 % při RRR 2:1, 45–50 % při 1:1). Všech 24 variant je po nákladech záporných. Short varianty jsou významně záporné (t −2,4 až −6,4).
- **Framework měsíční/týdenní VWAP + denní setup:** retest i 2SD fade podle kontextu (nad/pod W i M, růst/pokles M VWAP). Žádná z 24 kombinací není po nákladech kladná, nejlepší t 0,17.
- **Jak číst týdenní a měsíční VWAP** (G, závěr dne v pásmu → další dny):
  - Pod týdenním VWAP −1 až −2 SD: další den +0,10 ATR (t 3,0), za 5 dní +0,23 ATR.
  - Pod měsíčním −1 až −2 SD a pod −2 SD: za 5 dní +0,27 / +0,42 ATR (t 1,3–1,5).
  - Nad +1 / +2 SD je výsledek mírně podprůměrný.
  - Pásma W/M VWAP tedy fungují jako ukazatel **přeprodanosti pro swing longy** (stejný efekt jako RSI(2) z dřívějších testů), ne jako trendový filtr.

## 4. Volume profile a POC (`delta_vwap/out/H–L`)

- **POC jako magnet:** POC předchozího dne, týdne i měsíce se dotkne stejně často jako kontrolní úroveň ve stejné vzdálenosti na druhé straně od otevření (např. 0,25–0,5 ATR: 46,1 % vs 42,4 %, t 1,8; jinde ±3 p. b.).
- **Naked POC** (2–20 dní nedotčené): rozdíly −22 až +20 p. b. bez systému, malé vzorky. Magnet se nepotvrdil.
- **POC + delta:** první dotek včerejšího POC a delta za posledních 30 min.
  - Absorpce (cena do POC, delta opačně) má jen 129–140 případů, bez významnosti.
  - 1 ze 42 variant má t ≈ 2,0.
- **Pravidlo 80 %** (otevření mimo VA, 2× 30 min zpět uvnitř → druhá strana VA): denní VA **46 %**, týdenní 13 %, měsíční 3 %. Žádných 80 %.
- **Průchod přes kompozity / LVN vs HVN:** pohyb za dalších 60 minut je stejný v nízko- i vysokoobjemových zónách 20denního profilu (0,149 vs 0,150 ATR). Pokračování je 47–48 % ve všech zónách. Cena „neprolétá“ LVN rychleji.

## 5. Money management podle teorie her (`money_mgmt/out/`)

Long ES, páka do 5×, náklad 0,01 % obratu, 2010–2026. Bootstrap: 300 cest po 16 letech v blocích po 20 dnech.

| Pravidlo | CAGR | max DD | Sharpe | Alfa t | B&H se stejnou průměrnou expozicí (CAGR / DD) |
|---|---|---|---|---|---|
| Buy & hold 1× / 2× / 3× | 12,1 / 21,9 / 28,7 % | −34 / −60 / −77 % | 0,75 | – | – |
| Kelly plný / poloviční | 21,9 / 21,3 % | −74 / −65 % | 0,65 / 0,67 | 0,7 / 1,0 | 30,3 % / −82 % a 27,7 % / −74 % |
| Cílová volatilita 15 % | 11,3 % | −21 % | 0,71 | 0,6 | 15,3 % / −43 % |
| Martingale (2× po ztrátovém týdnu) | 17,8 % | **−91 %** | 0,59 | −0,4 | 20,3 % / −55 % |
| Anti-martingale / Paroli | 11,1 % | −47 % | 0,49 | −1,0 | 23,0 % / −62 % |
| D'Alembert | 23,1 % | −62 % | 0,70 | 0,5 | 17,0 % / −47 % |
| Fibonacci | 15,9 % | **−91 %** | 0,57 | −0,6 | 19,4 % / −53 % |
| Pyramidování +0,5× za každých 5 % pod maximem | 20,4 % | −59 % | 0,71 | 0,2 | 14,8 % / −41 % |
| Pyramidování za každých 10 % | 15,3 % | −43 % | 0,73 | 0,0 | 12,9 % / −36 % |
| **„Počítání karet“: 2× jen při přeprodanosti** (RSI(2) < 10 nebo pod W-VWAP −1 SD) | **20,9 %** | **−37 %** | **0,89** | **2,2** (1,2 / 1,8 po obdobích) | 14,6 % / −41 % |
| Riziko z týdenních propadů (q99 = 10 % účtu) | 20,5 % | −47 % | 0,77 | 0,9 | 22,4 % / −61 % |

- **Žádný systém sázení (martingale, Fibonacci, D'Alembert, Paroli, Kelly) nevytvoří edge.** Vyšší výnos vždy pochází z vyšší průměrné páky a leží na přímce „páka na buy & hold“, nebo pod ní (graf `money_management.png`).
  - Martingale a Fibonacci mají propad −91 %.
  - V bootstrapu má martingale 88 % šanci propadu horšího než −50 %, Kelly 100 %.
- **Pyramidování longů do poklesu** (tvoje myšlenka): s krokem 5 % dává CAGR 20,4 % / DD −59 %, tedy prakticky totéž jako stálá páka 2× (21,9 % / −60 %). Sharpe je horší (0,71 vs 0,75), alfa t 0,2. Dokupování do propadu zvýší výnos jen proto, že zvýší páku, a ta se projeví právě ve špatné chvíli (2020, 2022).
- **Jediné pravidlo s přidanou hodnotou** zvyšuje sázku jen tehdy, když existuje malá prokázaná výhoda: přeprodanost jako u počítání karet v blackjacku.
  - Sharpe 0,89 vs 0,75, alfa t 2,2, kladné v obou obdobích.
  - Bootstrap: medián CAGR 20,3 %, 5. percentil 11,2 %, P(DD < −50 %) 11 % (B&H 2×: 77 %).
  - **Je to stejný efekt přeprodanosti jako v Edge Factory a Swing Alpha. Money management ho jen zesiluje, sám ho nevytváří.**

## 6. Formace a obraty (`patterns/out/`)

- **Heikin-Ashi formace na objemových barech** (25k / 100k / 180k kontraktů): 4 svíčky × silná svíčka × pozice vůči VWAP × znaménko delty = 128 vzorů.
  - Pořadí vzorů z 2011–18 v letech 2019–26 nedrží (Spearman −0,21 až +0,21).
  - Ze 180 vybraných (nejlepší a nejhorší) mělo v testu stejné znaménko jen **51 %**, tedy hod mincí.
  - Nejstabilnější je 4 zelené HA svíčky, silná, nad VWAP, CD > 0 na 100k barech: +0,005 / +0,008 ATR na další bar (t 2,1 / 3,2), což je ≈ 0,3 b. Pokračování existuje, ale je o řád menší než náklady.
- **Co předchází skutečným obratům** (nový 60min low/high v RTH → odraz o 0,3 ATR dřív než prolomení o 0,1 ATR; základní podíl 18,8 % u dna, 17,5 % u vrcholu):
  - Obrat je častější:
    - po rychlém pohybu za posledních 30 min (dno: 27 % vs 13 %);
    - v den s velkým rozpětím (27 % vs 11 %);
    - při vysokém objemu posledních 5 min (25 % vs 16 %);
    - v první půlhodině RTH (27 %);
    - blízko včerejšího extrému a POC.
  - **Klasická delta divergence nefunguje:** když delta při novém low roste, obrat je méně častý (18,6 % vs 22,1 %).
  - LightGBM (walk-forward 2015–26) má AUC 0,63–0,65, ale předpovídá hlavně volatilitu. Top 10 % signálů je po nákladech −0,43 b./obchod (t −0,6 a −0,9).

## Celkový závěr
1. **Kalendář a hodiny:** dny v týdnu ani hodiny nemají stabilní směr. Robustní je jen volatilita: pondělí nejklidnější, 10:00 a 15:00 ET nejaktivnější. To pomáhá s volbou velikosti stopu, ne se směrem.
2. **Kumulativní delta, VWAP pásma, retesty, POC, pravidlo 80 %, LVN/HVN, HA formace:** ani jedno nedává po nákladech edge. Výsledky odpovídají náhodné ceně.
3. **Opakovaně se potvrzuje jen přeprodanost:** pod týdenním/měsíčním VWAP −1/−2 SD nebo RSI(2) < 10 → long na 1–10 dní. Money management, který v takové situaci zvýší sázku (2×), zlepšil Sharpe z 0,75 na 0,89 při menším propadu než B&H 2×.
4. **Systémy sázení z kasina a dokupování do poklesů** edge nevytvoří. Jen zvyšují páku. Martingale a Fibonacci mají propad −91 %.
5. **Bezpečná velikost:** po roce 2010 byl nejhorší propad uvnitř roku −35 % a uvnitř týdne −19 %. Expozice nad ~1,4× znamená, že takový rok sebere víc než polovinu účtu.
