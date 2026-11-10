# Mega sken: 166 milionů testů na ES 2008–2026 a strategie proti buy & hold

**Cíl:** projít co nejvíc kombinací vstupů, filtrů a výstupů a najít strategie, které porazí buy & hold. Každý objev se musí potvrdit ve dvou dalších obdobích a být lepší než náhodná kontrola.

## Jak sken funguje
- **Denní vrstva** (`daily.py`, `scan_daily.py`): rozhodnutí na závěru RTH, 4 725 dní (5/2008–9/2026).
  - 147 ukazatelů (momentum, RSI, vzdálenost od průměrů, volatilita, propady, gapy, VWAP D/W/M, delta, tvar dne, kalendář…) → 1 501 signálů.
  - Test = dvojice signálů × 5 režimů (vše, nad/pod MA200, vysoká/nízká volatilita) × 68 výstupů.
  - Výstupy: noc, další den, držení 1–20 dní a 60 kombinací SL 0,5–3 ATR × RRR 0,5–5, long i short, náklad 0,5 b.
- **Hodinová vrstva** (`hourly.py`): rozhodnutí na konci každé hodiny, 2011–2026, 249 signálů včetně delty a denního kontextu. Test = dvojice × hodina dne × 5 režimů × 29 výstupů (1–23 hodin, do závěru RTH, SL 0,1–0,5 ATR × RRR 1–3).
- **Období:** objev → potvrzení → holdout. Denní 2008–15 / 2016–20 / 2021–26, hodinová 2011–16 / 2017–21 / 2022–26.
- **Náhodná kontrola:** stejný sken s výstupy posunutými v čase (vazba signál → výsledek je zrušená, ostatní vlastnosti dat zůstávají). Ukazuje, kolik „objevů“ vznikne čistě náhodou.
- **Počet testů:** 146,7 mil. denních + 19,6 mil. hodinových = **166 mil. testů na skutečných datech** a dalších 626 mil. v náhodných kontrolách.

## Co sken našel (`out/sken_data_vs_nahoda.csv`)

Kandidát = |t| ≥ 4 v období objevu. Potvrzený = stejný směr a t ≥ 2 v obou dalších obdobích.

| Vrstva | Typ výstupu | Kandidátů: data / náhoda | Potvrzených: data / náhoda |
|---|---|---|---|
| denní | držení 2–20 dní | 298 414 / 186 880 | 5 601 / 6 197 |
| denní | long TP/SL (SL × RRR) | 754 667 / 700 681 | 16 157 / 24 757 |
| denní | short TP/SL | 1 244 409 / 1 087 846 | 33 412 / 34 717 |
| denní | **noc a další den** | 3 972 / 932 | **10 / 1,3** |
| hodinová | horizont 1–23 hodin | 2 921 / 328 | 5 / 0 |
| hodinová | long TP/SL | 7 902 / 4 193 | 46 / 2 |
| hodinová | short TP/SL | 8 967 / 4 288 | 68 / 4,5 |

- **Vícedenní držení a všechny kombinace SL × RRR na denních datech: žádný rozdíl proti náhodě.** Miliony „kandidátů“ vznikají překryvem po sobě jdoucích dnů. Potvrzených je stejně nebo méně než v kontrole.
- **Skutečný efekt je na horizontu do jednoho dne:** kandidátů je 4,3× víc než náhodou a potvrzených 7,5× víc. Z 3 972 kandidátů míří 3 800 stejným směrem: **slabost → růst přes noc a další den** (hlavně nad MA200: 2 220 kandidátů, v holdoutu průměrné t +2,9).
- **Intradenně existují skutečné, ale malé efekty** (potvrzených 119 proti ~7 náhodou). Velikost je 0,05–0,13 ATR na obchod, tedy jednotky bodů. Nejčastější: po prudkém poklesu v první hodině RTH (9:00–10:00) pokračuje pokles (short SL 0,2 ATR RRR 1: +0,13 / +0,07 / +0,09 ATR nad průměr ve třech obdobích, ~40 případů na období).
- Kontrolní náhodné signály (sudý den, ciferný součet, náhodná čísla) se mezi potvrzenými neobjevují častěji než ostatní.

## Skóre slabosti (`score.py`, postavené jen z dat do roku 2020)

- 20 signálů, které se nejčastěji vyskytly v kandidátech s kladnou další nocí/dnem (objev 2008–15, souhlas 2016–20): RSI(3) ≤ 5 %, RSI(5) ≤ 10 %, stochastik 5 a 14 dole, týden v nejhorším decilu, cena hluboko pod MA5, slabý MACD, poslední hodina slabá, velké rozpětí posledních 3 dnů, poslední den měsíce a další.
- Skóre = počet splněných signálů. Prahy z let 2009–2020: „slabost“ ≥ 6 (nejvyšších 20 % dnů), „silná slabost“ ≥ 10 (nejvyšších 5 %).

Výnos dalšího dne podle skóre:

| Období | Bez slabosti | Slabost 6–9 | **Silná slabost ≥ 10** | Všechny dny |
|---|---|---|---|---|
| 2009–2015 | +0,02 % | +0,07 % | **+0,44 %** (98 dní, t 3,8, růst 69 %) | +0,06 % |
| 2016–2020 | +0,03 % | +0,03 % | **+0,51 %** (67 dní, t 1,2, růst 61 %) | +0,06 % |
| **2021–2026 (holdout)** | +0,02 % | +0,03 % | **+0,46 %** (84 dní, t 3,0, růst 66 %) | +0,05 % |

Silná slabost nastává asi 15 dní v roce a další den vydělá v průměru 8× víc než běžný den. Efekt je stejně velký v holdoutu jako v období objevu.

## Strategie proti buy & hold (`out/score_strategie.csv`, 6/2009–9/2026, náklad 0,5 b. na kontrakt při každé změně)

| Strategie | CAGR | Sharpe | Max propad | Alfa/rok (t) | Let lepších než B&H | CAGR 2021–26 |
|---|---|---|---|---|---|---|
| Buy & hold 1× | 12,5 % | 0,78 | −34 % | – | – | 10,8 % |
| S1: slabost → 2× | 19,3 % | 0,85 | −33 % | +2,7 % (1,4) | 17 z 18 | 17,7 % |
| **S2: slabost 2×, silná slabost 3×** | **25,4 %** | **0,94** | −38 % | **+6,8 % (2,2)** | **17 z 18** | **24,4 %** |
| S3: slabost → +1× jen přes noc | 15,5 % | 0,83 | −33 % | +1,5 % (1,1) | 15 z 18 | 14,4 % |
| S5: v trhu jen při slabosti (22 % dnů) | 7,0 % | 0,73 | −16 % | +2,7 % (1,4) | 5 z 18 | 7,1 % |
| **S6: jen při slabosti, silná 2×** | **13,0 %** | **0,88** | **−23 %** | +6,8 % (2,2) | 7 z 18 | 13,6 % |

- **S2 zhodnotila 1 → 55,4, buy & hold 1 → 8,1.** V holdoutu 2021–26 má CAGR 24,4 % proti 10,8 % a Sharpe 0,95 proti 0,71.
- **S6 dosáhla výnosu buy & hold (13,0 % vs 12,5 %) s o třetinu menším propadem**, přitom je v trhu jen asi pětinu dnů.
- Jednoduchá pravidla bez skenu (`out/strategie_vs_BH.csv`, 2012–2026): RSI(2) < 10 → 2× dává CAGR 18,0 % vs 12,3 %, Sharpe 0,89 vs 0,79, propad −32 % vs −34 %, lepší než B&H ve 13 z 15 let.
- **Strojové učení** (ridge, LightGBM, walk-forward na 147 ukazatelích): korelace předpovědi s dalším dnem jen −0,01 a +0,02. LightGBM 1 + z: CAGR 18,3 %, Sharpe 0,79, tedy bez zlepšení proti jednoduchému pravidlu.
- Futures nesou financování v ceně, takže páka 2–3× nemá další úrokový náklad. Vyžaduje ale margin a snese propad: S2 má nejhorší propad −38 %.

## Omezení
- Alfa S2 má t 2,2 za 17 let a v holdoutu 1,7. Je to nejsilnější výsledek celého výzkumu, ale ne jistota.
- Výběr signálů do skóre používal data jen do roku 2020. To, že slabost funguje, jsme ale věděli už z dřívějších testů na celé historii, takže holdout není úplně „slepý“.
- Páka 3× se zapíná právě po poklesech. V roce 2020 a 2025 by propad dosáhl −31 až −38 %.
- Vstup a výstup na závěrečné ceně RTH (15:59); skluz nad 0,5 b. není započtený.
- Hodinová vrstva: prahy četnosti nechaly 249 signálů; footprint a tick data v ní nejsou.

## Kam dál (brainstorming)
1. **Zpřesnit skóre slabosti:** váhy místo prostého počtu, výstup při prvním vyšším závěru místo jednoho dne, noční vs denní část, chování v medvědím trhu (pod MA200).
2. **Intradenní pokračování po propadu v první hodině** (short v 10:00): samostatný test s reálnými náklady, ~8 obchodů ročně.
3. **Trojice signálů** na horizontu do 1 dne (dalších ~200 mil. testů) a jemnější časování vstupu (15:00 vs 15:59 vs noc).
4. **Další trhy a data:** NQ, VIX a termínová struktura, dluhopisy, šíře trhu. Tato data nemáme a mohla by přidat nezávislé signály.
5. **Footprint z tick dat** přes připravený export ze Sierra Chart.
6. **Paper trading S2 / S6** se zamčenými pravidly a porovnáním s testem.

Grafy: `out/charts/` (objevy vs náhoda, rozdělení t, skóre → další den, equity, propady).
