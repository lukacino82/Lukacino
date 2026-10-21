# Knihovna zdrojů systematického tradingu – rešerše (21. 10. 2026)

Rešerše přes webové vyhledávání. Přímé stažení stránek je v našem prostředí blokované, čísla jsou z abstraktů a shrnutí. Tam, kde jde o tvrzení prodejců, je to označené. U každého mechanismu je vazba na naše výsledky z ES2008.

## 1. Kde hledat – komunity, agregátory, huby

| Zdroj | Co to je | Hodnota pro nás |
|---|---|---|
| [Quantocracy](https://quantocracy.com) | Agregátor quant blogů („Quant Mashup“) | Denní přehled nových studií |
| [Quantpedia](https://quantpedia.com) | Databáze strategií z akademických paperů | Katalog mechanismů k testu |
| [Alpha Architect](https://alphaarchitect.com/a-compilation-of-evidence-based-trading-ideas/) | Research blog, databáze stovek trading idejí | Shrnutí akademických paperů |
| [AQR data library](https://www.aqr.com/Insights/Datasets/An-Academic-Quality-Data-Library-for-Practitioners) | Volně dostupné řady faktorů a paperů | Benchmark pro trend / value / momentum |
| [Newfound Research](https://blog.thinknewfound.com/author/admin/) | Research o trendu, rebalancing timing luck | Teorie timing luck, trend |
| [Robot Wealth](https://robotwealth.com), [QuantStart](https://www.quantstart.com/about/) | Praktický výzkum a výuka | Metodika backtestu |
| [Concretum Research](https://concretumgroup.com/beat-the-market-an-effective-intraday-momentum-strategy-for-sp500-etf-spy/) (Zarattini) | Intradenní momentum na SPY/ES | Přímo náš trh |
| [QuantConnect forum](https://www.quantconnect.com/forum/list/368/community) | Komunita + LEAN engine, výzkumné články | Replikace strategií |
| [Wilmott forum](https://forum.wilmott.com/) | Profesionální quant fórum (Trading, Technical) | Odborné diskuze, náročné |
| [NexusFi (futures.io)](https://nexusfi.com/a/market-structure/footprint-charts-order-flow) | Futures fórum, Sierra Chart, order flow | Praktické dotazy k Sierra Chart |
| r/algotrading, Discord Quant Talk (~2,8 tis. členů) | Komunitní diskuze | Nápady, ne důkazy |
| [awesome-systematic-trading](https://www.context-awesome.com/list/paperswithbacktest/awesome-systematic-trading) (GitHub, ~7,8k ★) | Seznam knihoven, strategií, knih | Nástroje (vectorbt, backtrader, QuantStats) |
| Nuclear Phynance | Uzavřené fórum prop/quant traderů | Aktuální stav neověřen |

Knihy (praktici):
- Robert Carver: *Systematic Trading*, *Leveraged Trading*, *Advanced Futures Trading Strategies* (ex-AHL).
- Ernest Chan: *Quantitative Trading*, *Algorithmic Trading*.
- Timothy Masters: *Testing and Tuning Market Trading Systems* (permutační testy).
- Marcos López de Prado: *Advances in Financial Machine Learning*.
- Ralph Vince: *Handbook of Portfolio Mathematics*.
- Chen & Ankenman: *The Mathematics of Poker*.

## 2. Jak nepodlehnout overfittingu (statistika)

- **Harvey, Liu, Zhu (RFS 2016)**: kvůli data-miningu má nový faktor potřebovat **t ≈ 3,0**, ne 2,0. Podle autorů je většina publikovaných nálezů pravděpodobně falešná. → U nás: jen crisis allocator (t 2,4), bez vysoké vol (2,4) a pre-FOMC (2,0) se blíží. Nic nepřekonalo 3,0.
- **López de Prado – PBO (Bailey a kol., J. Comp. Finance 2015)**: pravděpodobnost přeučení backtestu přes kombinatorickou křížovou validaci (CSCV). Dále deflated Sharpe ratio (penalizace za počet pokusů) a purged / combinatorial purged CV.
- **Timothy Masters – permutační test**: kolikrát by náhodně zpermutovaná data daly stejně dobrý výsledek.
- **McLean & Pontiff (JF 2016)**, 97 anomálií:
  - mimo vzorek o **26 %** nižší výnos (data-mining);
  - po publikaci o **58 %** nižší;
  - ~32 % tedy „vyžerou“ investoři, kteří o anomálii vědí.
- **Cederburg a kol.**: vol-managed portfolia mají v reálném čase (out-of-sample) většinou horší Sharpe než původní. Pozor na regresní alfu, která není obchodovatelná.

## 3. Mechanismy („cinklé kostky“) z literatury vs. naše data

| Mechanismus | Co říká výzkum | Naše ES2008 | Další krok |
|---|---|---|---|
| **Volatilitou řízená expozice** (Moreira & Muir) | Méně rizika při vysoké vol: alfa 4,9 %, Sharpe trhu +25 %. Kritika: mimo vzorek slabší. | Vol target alfa +2,1 % (t 1,25), crisis allocator t 2,4 | Hotovo, základ portfolia |
| **Nucené toky vol-control a CTA** (Nomura, GS) | Při skoku vol prodávají desítky miliard (např. ~84 mld. USD za 2 týdny, ~108 mld. USD od března 2026), při poklesu vol nakupují zpět | Odpovídá crisis allocatoru (nákup po panice) | Test „vrchol realizované vol → nákup“ |
| **Pre-FOMC drift** (Lucca & Moench, JF 2015) | 24 h před FOMC +33 bp vs. +1 bp ostatní dny (1994–2011), >80 % prémie akcií | Pre-FOMC t 2,0, zesílil po 2018 | Hotovo, samostatná vrstva |
| **Overnight drift** (Boyarchenko, Larsen, Whelan) | Prémie vzniká hlavně 2–3 h ET (≈3,6–3,7 %/rok). Silné noční reverze po výprodeji (inventář dealerů). **Od 2021 ≈ 0** (Liberty Street 2026). | Výnos ES vzniká přes noc. Noční držení se po nákladech nevyplácí. | **Test: noční reverze po RTH výprodeji + rozpad po 2021** |
| **Intradenní momentum** (Gao, Han, Li, Zhou, JFE 2018) | 1. půlhodina předpovídá poslední půlhodinu, silněji ve dnech vysoké vol a zpráv | Netestováno přesně | **Test na ES 1min** |
| **Noise-area momentum** (Zarattini, Aziz, Barbon) | Autoři: 19,6 %/rok, Sharpe 1,33 (2007–2024, nezávisle neověřeno) | Naše replikace na 1×: alfa +0,7 %/rok (t 0,8), kladná ve vysoké vol 2022–23 | Varianta s pákou / jen vysoká vol |
| **Time-series momentum** (Moskowitz, Ooi, Pedersen 2012) | 58 futures, 12M lookback. Kritika (Kim, Tse, Wald): efekt hlavně z vol-scalingu, 2009–13 mizí. | TSMOM 12M na ES bez alfy | Potvrzeno: na samotném ES ne |
| **Penzijní rebalancing** (Harvey, Mazzoleni, Melone 2025) | Když jsou akcie overweight, fondy prodávají → −17 bp další den, predikovatelné a front-runovatelné | Netestováno | **Test: konec měsíce/kvartálu po silném měsíci akcií** (lépe s T-note futures) |
| **Dash for cash / turn of month** (Etula a kol., RFS 2020) | Výplaty na konci měsíce: tlak na T-3 před koncem měsíce a reverze, vysvětluje turn-of-month efekt | TOM bez alfy | **Test: T-3 reverze na ES** |
| **Variance risk premium** (Bollerslev, Tauchen, Zhou, RFS 2009) | Rozdíl implikované a realizované variance předpovídá výnos akcií, nejlépe na ~kvartál | Netestováno | Potřebujeme VIX |
| **Dealer gamma / OPEX** | Jen materiály prodejců (SpotGamma), žádná nezávislá validace. OPEX efekt pre-2008 kladný, nyní nekonzistentní. | Netestováno | Nízká priorita |
| **Okna zákazu buybacků** | Hlavně komentáře (Goldman: objem buybacků −35 % při začátku blackoutu), žádný rigorózní test | Netestováno | Nízká priorita |
| **Hluboký drawdown → nákup** (T. Rowe Price, 1940–2025) | Po −20 %: 12M výnos 17,3 % vs. 12,8 %, šance na ztrátu 10,8 % vs. 21,6 % | Odpovídá crisis allocatoru | Hotovo |
| **Falešná zotavení** | V 17 z 26 medvědích trhů (od 1929) rally > 10 %, průměrně ~9 % a ~20 dní. 2007–09: 12 rally > 5 %. | Hlavní slabina reverzních strategií (2022) | **P10: filtr falešného zotavení** |

## 4. Order flow, footprint, mikrostruktura

- **Order flow imbalance** (Cont, Kukanov, Stoikov 2014): krátkodobé změny ceny lineárně vysvětluje nerovnováha na best bid/ask. Jde ale o **současný** vztah na datech order booku, ne o předpověď.
- **VPIN** (Easley, López de Prado, O'Hara): „toxicita toku“ před flash crashem 2010. Andersen & Bondarenko: VPIN maximum přišlo **až po** krachu, prediktivní síla je hlavně mechanická vazba na objem.
- **Footprint, absorpce, number bars**: vyhledávání nenašlo **žádný akademický ani nezávislý důkaz** edge. Jen definice prodejců a příklady z fór. Shoduje se s naším výsledkem: delta divergence = šum, absorpce mimo RTH 1–3 bp.
- **Data pro footprint**: Sierra Chart ukládá ticky v .scid (formát „Intraday Data File Format“). Menu Edit → Export Bar Data to Text File exportuje bary. Pro per-trade data je potřeba 1-tick graf nebo parser .scid.

## 5. Money management, poker, teorie her

- **Kelly** (Thorp):
  - Full Kelly má i při přesných vstupech ~50% šanci, že účet někdy klesne na polovinu.
  - 2× Kelly = nulový dlouhodobý růst.
  - ½ Kelly ≈ 75 % růstu při ~25 % rozptylu.
  - Odhad edge z krátkých vzorků bývá nadsazený, proto ¼–½ Kelly.
- **Optimal f / leverage space** (Vince; matematicky Maier-Paape 2013): maximalizace růstu s omezením, např. drawdown > 20 % nejvýš s pravděpodobností 1 %. Hodí se pro náš cíl „hard DD 40 %, design 30 %“.
- **Mathematics of Poker** (Chen & Ankenman): teorie her a rovnováha jako způsob myšlení. Bankroll řeší jen okrajově.
- **Teorie her v obchodování**:
  - Spooner & Savani (IJCAI 2020): adversarial RL pro market making, Nashova rovnováha.
  - Cesa-Bianchi a kol. (2024): market making s minimalizací lítosti.
  - CFR přímo pro obchodování veřejně skoro chybí. EquiLibre to nepublikuje.

## 6. Co z rešerše plyne pro nás

1. Naše výsledky sedí s literaturou: robustní je řízení expozice podle vol, nákup panik (nucení prodejci) a pre-FOMC. Trend na samotném ES a order-flow vzorce bez mechanismu nedrží.
2. **Nové testovatelné hypotézy na ES2008 (data máme):**
   - (a) noční reverze po RTH výprodeji a její rozpad po 2021;
   - (b) intradenní momentum 1. → poslední půlhodina ve dnech vysoké vol;
   - (c) T-3 / turn-of-month reverze (dash for cash);
   - (d) proxy penzijního rebalancingu na konci měsíce a kvartálu;
   - (e) vrchol realizované vol → zpětné nákupy vol-control fondů;
   - (f) filtr falešného zotavení (P10).
3. **Data, která chybí**: VIX (VRP), T-note futures (rebalancing), COT, opční OI (gamma), tick data ze Sierra Chart (footprint).
4. Laťka úspěchu: t ≥ 3 nebo PBO < 0,2. Počítat s tím, že po publikaci se efekt zmenší o ~30–60 %.
