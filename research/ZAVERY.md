# Závěry výzkumu ES (stav k 11. 10. 2026)

Data: ES 1min back-adjusted, květen 2008 – září 2026 (6,4 mil. barů). Všechny testy po nákladech,
s oddělenými obdobími (objev / ověření / out-of-sample) a srovnáním s náhodou a buy & hold.

## 1. Alpha Audit (`alpha_test/`)
- 29 strategií z „alpha brainstorm“ (ChatGPT Phase 1–4) přepočteno na surových datech. Žádná neprošla všemi 7 testy robustnosti.
- Čísla z ChatGPT se nereplikují (např. +9,75 b./obchod → −2,27 b.).
- Open ± X jako fade systém nefunguje. Breakout long s ATR škálováním je na hraně (t ≈ 1,6).
- 3 kandidáti na paper trading: Deep Gap + VWAP + delta divergence, DD2 PDL sweep, Bull 10–12 delta divergence.

## 2. ES Alpha Map – Mattia + 13 rodin (`mattia/`)
- Vault Break a VWAP Pullback: po nákladech nula nebo ztráta. Overnight Bias funguje jen long a jen od roku 2018.
- Prop-firm challenge: kombinace strategií selže častěji, než projde. Výhoda je v „geometrii“ pravidel prop firmy, ne v edge.
- Hodinová sezónnost vybraná dopředu (bez overfittingu) nedrží.
- Robustní je řízení expozice: vol-managed ES + nekorelované vrstvy dají Sharpe ~0,9 a DD −19 %.
  B&H se stejnou volatilitou má Sharpe 0,62 a DD −36 %.

## 3. Edge Factory (`edge_factory/`)
- 3 157 hypotéz: kalendář, hodiny, dny v týdnu, VWAP retesty, delta divergence (minuty až měsíce), absorpce, stop-hunty. Rozdělení výsledků odpovídá náhodě.
- Drží jen 3 malé efekty:
  - RSI(2) přeprodanost → long na další den;
  - po novém 52týdenním maximu pomalejší růst (nepřidávat páku na ATH);
  - absorpce mimo RTH, ale jen 1–3 bp, což sotva pokryje náklady.
- ML (LightGBM, walk-forward): intraday ≈ nula, denní horizont IC ~0,10.
- Money management edge nevytvoří, jen ji zesílí nebo zničí. Kelly při nulové edge = 0.

## 4. Loss Streak Lab – vysoké RRR (`high_rrr/`)
- Krátké série 3–5 ztrát jsou čistá statistika win rate.
- Dlouhé série (10–20+) přicházejí 2–10× častěji než náhoda. Mají dva zdroje:
  - (a) pevný stop malý vůči volatilitě: pod 0,2 ATR se trefí v 80–90 % obchodů;
  - (b) rozjetá korekce: 5denní rozsah > 4 ATR, cena pod týdenním VWAP −2σ, drawdown 3–7 %.
- 486 tisíc kombinací filtrů: nic neprošlo přísným testem.
- Breakeven a trailing téměř všude snižují expectancy. Pauza po sérii nepomáhá.

## 5. Swing Alpha SW01–SW05 (`swing_alpha/`)
- Pokračovací logika (migrace POC/VA, zarovnání VWAP D/W/M, breakout z kompozitu, Bull/Bear režim) má po odečtení driftu nulový až záporný nadvýnos. Na 1–20 dní ES vrací k průměru.
- Funguje opak, long po bearish extrému:
  - „jádro fade“ = close pod low kompozitu, retest prolomené hrany, plně bear zarovnání VWAP;
  - 10 dní: +0,66 ATR/obchod vs +0,35 ATR „long každý den“, v trhu jen 52 % času;
  - drží 2009–18 i 2019–22, v letech 2023–26 na 10 dní ne.
- Short: záporný ve všech variantách (drift).
- Režimy jsou perzistentní (Bull ~4,8 dne, P(pokračuje) 0,68 → 0,90), ale nadvýnos nenesou.
- SL: 0,5 ATR je záporný u všeho (série 14–29 ztrát). 2 ATR + RRR 1:3–1:5 je nejlepší (série ~8).
  Časový exit 10–20 dní ≥ „chytré“ exity.
- Výběr jedné nejlepší konfigurace ve walk-forward = nula. Spolehnout se dá jen na rodinu pravidel.

## 6. Realita výnosů a tvůj NQ test
- Výnos ≈ edge (R) × počet obchodů × riziko na obchod.
  Stovky % ročně spolehlivě jen při edge ≥ 0,2 R, stovkách obchodů a riziku 1–2 % (horní ~1 % traderů).
  Bez edge to je loterie s 90% šancí na půlení účtu.
- Literatura: ziskových day traderů < 1 % (Tchaj-wan); 97 % ztrátových (Brazílie, futures).
- NQ sim (42 obchodů, SL 50 b. / TP 500 b.):
  - 4 výhry, t = 0,38, 28 ztrát v řadě, DD −28,6 tis. USD;
  - buy & hold 1 kontraktu ve stejném období +39 tis. USD;
  - zisk stojí na jednom obchodu se 2 kontrakty;
  - stop 50 b. byl ~0,2 ATR;
  - výhry trvaly 4–14 dní, takže je to swing, ne intraday.

## 7. Co platí do budoucna
1. Stop vždy z denního ATR (Sierra: denní graf + ATR 14 Simple).
   NQ dnes ATR ~440 b. (odhad 2023–26: 0,95–2,7 % ceny, medián ~1,3–1,5 %).
   Intraday ≥ 0,5 ATR, swing 1,5–2 ATR.
2. Velikost = riziko v USD / (SL v bodech × hodnota bodu). MNQ pro menší účet. Riziko 0,5–1 % na obchod.
3. Stavět long-only reverzní swing (koupě po výprodeji, držení 5–20 dní, SL 2 ATR), ne intradenní pattern trading.
4. Každý systém měřit proti buy & hold a „vstupu každý den“ se stejným exitem.
5. Edge prokázat čísly: 200–800 obchodů podle velikosti edge, deník se štítkem setupu.

## Další kroky
- Export denních + 1min dat NQ ze Sierra Chart → přepočet ATR, swing systému a tvého 1:10 systému na NQ.
- Spojit RSI(2), jádro fade a denní ML skóre do jednoho skóre přeprodanosti.
- Paper trading se zamčenými pravidly 3–6 měsíců.

## 9. Rešerše zdrojů a mechanismy z literatury (`ZDROJE.md`, `mechanisms/`)
- Rešerše (Drive 06): laťka pro nový objev je t ≈ 3 (Harvey–Liu–Zhu). Po publikaci anomálie klesne výnos o 26–58 % (McLean–Pontiff). Pro footprint jsme nenašli žádný nezávislý důkaz edge.
- Testy na ES2008 (Drive 07): tři tokové edge fungovaly do 2020 a v letech 2021–26 jsou nulové:
  - okno 02–03 ET (t 4,5 → 0,4);
  - intradenní momentum;
  - poslední 4 dny měsíce po slabém měsíci (+0,95 / +1,27 % → −0,07 %).
- Okno 02–03 nebylo na 1 ES nikdy obchodovatelné (0,21 b. hrubě < 0,5 b. náklad).
- Zpětné nákupy po vrcholu vol: směr kladný, jen 12 signálů. Falešná zotavení: 7 ze 14, bez spolehlivého filtru z ES dat.
- Závěr: edge založené na kalendáři a známých tocích stárnou. Každý systém potřebuje průběžný monitoring a kill kritérium.

## 10. Obrácené RRR a hodiny (`inverse_rrr/`, Drive 08)
- 798 784 kombinací (čas × TP × SL × podmínka × horizont). Win rate náhodného vstupu = SL/(TP+SL) přesně jako náhodná procházka. 1:10 vyhraje 91 %, ale expectancy je stále drift − náklad (−0,3 až −0,4 b. intradenně v 09:30).
- Long obrácené RRR vybrané na 2008–17 v OOS 2022–26 selhaly (−1,5 b./obchod, kladná edge jen u 10 %). Klidný vzorek bez černé labutě vybírá právě pravidla, která pak zničí rok jako 2022.
- Hodina sama směr nedává. P(+15 b. do close) závisí hlavně na ATR roku (09:30: 7 % v roce 2017, 71 % v roce 2022), proto TP/SL v ATR. Před ziskem +15 jde cena v 25 % případů 12 b. proti.
- Přežily dva kandidáti na paper trading:
  - (A) intradenní momentum po první hodině RTH: short v 10:00 po propadu ≥ 0,3 ATR, OOS +5,3 b., vybráno jen na 2008–17;
  - (B) long v 09:00 po poklesu ≥ 10 b. kolem dat v 8:30, TP 6 / SL 30, 17/17 ziskových let, OOS t 2,2, jen čas 09:00.

## 11. Obrácené RRR s TP/SL v ATR – 116 signálů, 2,2 mil. kombinací (`inverse_rrr/VYSLEDKY_ATR.md`, Drive 17)
- Výběr na 2008–17, test 2018–26. Top 20 long obrácených RRR mělo v OOS kladnou edge jen ve 25 % (náhodný výběr 55 %).
- Automatické portfolio 25 signálů (riziko 0,5 %/obchod):

  | Období | CAGR | Sharpe |
  |---|---|---|
  | 2009–17 | 15–30 % ročně | 1,44 |
  | 2018–26 | 1,3 % | 0,19 |
  | B&H 2018–26 | 9,5 % | 0,65 |

  Zásahy SL se po roce 2018 ztrojnásobily.
- Výběr rodin pravidel: v letech 2018–26 také ≈ 0. Korelace s ES 0,03, v letech 2022–26 jako doplněk B&H zvedá Sharpe 0,52 → 0,78.
- Jediný konzistentní vzor je momentum v medvědím režimu: ES pod MA200, pohyb ±1 ATR od otevření session → obchod ve směru do close. +0,06 ATR/obchod, kladné ve všech obdobích, ale t 1,45 a jen ~10 obchodů ročně.
- Obrácené RRR samo edge nevytvoří. Automatizace s ATR je triviální, problém je v očekávané hodnotě, ne v technice.

## 12. Livermore: pivotal points, pyramidování, Market Key (`livermore/`, Drive 21)
- 42 variant pravidel (průraz 20/55/252D, pyramida 20/20/20/40 %, stop 2 ATR nebo 10 %, časový stop, výstup na reakci, Market Key 2–4 ATR).
- Žádná varianta nemá prokazatelnou alfu: nejlepší t = 1,58, Sharpe 0,80 vs B&H 0,74, CAGR 7,6 vs 9,4 %.
- Pyramidování na ES ve všech dvojicích zhoršilo výsledek proti plné pozici.
- Náhodné vstupy se stejnými výstupy byly lepší než průraz 55D (p = 0,92).
- Profil odpovídá Livermorovi (payoff 2–11×, top 10 % obchodů = 35–56 % zisku), ale B&H to nepřekoná.
- Trendový princip má smysl jen jako trend-following přes mnoho trhů. Na samotném ES jsou z Livermora užitečné jen pravidla řízení rizika.
- One-day reversal (býčí i medvědí, s objemem i bez, po 20denním extrému): excess proti driftu je nevýznamný ve všech 35 kombinacích (|t| ≤ 1,5). Systém long na 5 dní: CAGR 0,5 % vs B&H 9,4 %.

## 13. Hypotézy ze tří knih: HTTIS 1940, Wyckoff o Livermorovi, Livermore Lines (`livermore/books_hypotheses.py`, Drive 23)
- Otestováno 13 hypotéz: pivotal points, kulatá čísla, nákup nového maxima po normální reakci, varovná abnormální reakce, objem v reakcích, test pivotu, „nekupuj kvůli poklesu“, nákup v panice, prodej při překoupenosti, Wyckoffovy výstupy 3:1 s časovým stopem a Market Key v %.
- Ve směru, jak to tvrdí knihy, nemá žádná prokazatelnou edge (|t| ≤ 1,7).
- Dva výsledky jdou proti knihám:
  - první close nad novou stovkou má po 10 dnech excess −0,52 % (t −2,4);
  - nákup po poklesu 20D ≥ 5 ATR má po 60 dnech excess +2,3 ATR (t 2,1, n 16, v letech 2018–21 záporný). To je známý mean-reversion ES, ne nový signál.
- Systémy s Wyckoffovými výstupy mají alfu t ≤ 1,3, kladné R/obchod je jen drift. Market Key 5–10 % nepřekonal B&H.
- Top-down výběr trh/odvětví/tandem (Livermore Lines, Key Price) potřebuje mnoho akcií, na ES netestovatelné.

## 14. Cyklové levely (BCL) jako obchodní úrovně (`cycle_levels/`, Drive 24)
- Mřížka z grafu: červené levely ×1,38944 (2908 · 4041 · 5615 · 7801), cyklus dělený na čtvrtiny. Test na 1min ES převedeném na cash 2018–2026, proti 200 náhodně posunutým mřížkám.
- Jemné intradenní levely (rozestup 34–270 bodů, 21 000 doteků): žádný efekt.
- Velké levely z grafu: odraz o 0,5 rozestupu 59,6 % vs 51,2 % (p 0,01). Červené 65 %, poloviny 63 %, platí v obou obdobích. Fade 0,5/0,5 dává +0,21 R.
- Je to ale jen 89 doteků a efekt chybí při 0,25 a 1 rozestupu. Počet významných konfigurací (8 z 80 na hladině 10 %) odpovídá náhodě.
- Dokončování cyklů je stejné jako u náhodných mřížek, je to drift.
- Nejzajímavější náznak zatím, ale neprokázaný. Rozhodne test na historii 2000–2018 (export z MT4).

## 15. BCL – logika čar Forex Rebel a test 2008–2026 (`bcl/`, Drive 25)
- Logika z excelu kurzu: cyklus = 0,7 × cena / páka, tedy pohyb k margin callu plně zapákovaného účtu.
  - Konstanta 70 → 2,8028 % (D1), 700 → 28,028 % (W1).
  - Červené čáry geometrické, mezičáry lineární čtvrtiny. Sedí na grafy ±0,03 bodu.
- Data: US500Cash ekvivalent. 2018–26 přesně podle brokera; 2008–18 rekonstrukce z ES2008 (±2–4 body).
- D1 čáry: 16 000 doteků, 392 variant TP/SL, celkové p = 0,65, výsledek jako u náhodných čar.
- W1 čáry: 196 doteků, celkové p = 0,49. Předem stanovená hypotéza (odraz 1/8 cyklu na červených a polovičních) mimo vzorek 2008–18 neprošla (R +0,01, p 0,61). Samotné červené kladné v obou obdobích, ale n = 26, p 0,14.
- H1 čáry (konstanta 7, 2018–26, 337 000 doteků): celkové p = 0,39, excess ±0,01 R, po nákladech ztráta.
- Čáry samy edge nemají na žádném timeframe (7 / 70 / 700). Neplatí ani to, že „čáry určují TP/SL“.
- Dodatek po master dokumentu (Drive 26): vzorec Δ = R·K/9990 je shodný s naším. Síť se přesouvá po dokončeném cyklu.
  - Otestováno kotvení na kauzálních pivotech (R = pivot, K = 70: 752–1 086 pivotů) a kontext trendu (SMA200) u pevné i pivotové sítě.
  - Celkové p 0,29–0,93, žádná varianta nepřekonala náhodně posunuté kotvy.
  - K = 700 má za 18 let jen 3–9 dokončených cyklů, nejde otestovat.

## 16. RRR matice SL 6–100 b. × RRR 1:1–1:25, časová okna, ATR, stop-hunty, sonda, ML (`rrr_matrix/`, Drive 27)
- **Rozsah:** 93 666 hodinových vstupů na směr a horizont (intraday / 5 dní / 20 dní), 2011–2026. SL v bodech i v ATR timeframe (H1/D1/W1), náklad 0,5 b.
- **Win rate = náhodná procházka** (SL/(SL+TP)). RRR samo edge nedává.
  - Intraday: 1:10–1:25 skoro nikdy nedojde na TP, výsledek 0 až −0,05 R long a až −0,13 R short.
  - 5–20 dní long kladné jen díky driftu (+0,05 až +0,2 R), short záporný.
- **Menší timeframe = horší** (náklady, malý SL). Nízké RRR má mnohem kratší série ztrát (max 13–33) než vysoké s pevnými body (stovky až tisíce, protože TP v bodech v klidných letech nedojde).
- **Optimalizace oken:** drží jen hodina (večerní Globex = noční drift, +0,02 R OOS). Den v týdnu a měsíc OOS nedrží (výběr měsíce −0,27 R).
- **Alfa proti B&H 2019–26** (B&H z cash řady 15,3 % ročně): nejlepší ATR 20D long +8 %/rok, ale t 1,0 a DD −45 %. Žádná kombinace s alfou ≥ 3 % a t ≥ 2. Pevný malý SL s rizikem 1 % = páka, účet se zničí.
- **Stop-hunt (PDL/ONL sweep a návrat) ± kumulativní delta ± bias:** stejné jako náhodný vstup po signálu (−0,04 až +0,05 R, t ≤ 1,6).
- **Sondovací pozice** zhoršuje o 0,01–0,03 R. Vstup níž (průměrování) ≈ přímý vstup.
- **ML walk-forward (LightGBM, 18 rysů):** AUC 0,6–0,8 předpovídá volatilitu, ne směr. Výběr obchodů nestabilní mezi roky. Self-learning kód je technicky proveditelný, edge ale nevytvoří.
