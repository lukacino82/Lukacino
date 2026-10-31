# Kotvy, doba do dosažení, protipohyb a seance (zadání z 31. 10. 2026)

**Otázka:** Cenový cíl (kotva) může být správný, ale načasování špatné. Cena nejdřív jede proti pozici a cíle dosáhne až později. Je dosažení kotvy skutečně pravděpodobnější než náhoda a jak velký protipohyb mu předchází? (Hypotézy H1, H3, H4, H5 ze zadání.)

**Data a metodika:**
- ES 1min (back-adjusted), 2011–2026, časy v ET (letní čas je ošetřený).
- Události: každou celou hodinu, když je cena 0,1–4 denní ATR od kotvy. Celkem 1,07 mil. událostí, z toho 714 tisíc ve vzdálenosti 0,25–2 ATR.
- **14 kotev:**
  - VWAP denní, týdenní, měsíční (pásma SD se v tomto testu nepoužívají);
  - POC, VAH a VAL předchozího dne, týdne a měsíce (70% value area z volume profile, ne SD pásma);
  - High a Low předchozího dne.
- **Obchod „k kotvě“:** vstup na uzávěrce hodiny, cíl = kotva, stop 0,5 / 1 / 2 ATR nebo žádný, horizont 2h, 3h, 12h, do konce RTH dne, 1d, 2d, 5d. Náklad 0,5 b., při současném dotyku stopu a cíle platí stop.
- **Kontrola:** zrcadlová úroveň ve stejné vzdálenosti na druhé straně ceny. Odstraní volatilitu a denní dobu. Zbývá drift trhu, který se vyruší průměrem událostí s kotvou nad a pod cenou.
- **Statistika:** klastry po dvou týdnech. První pokus s klastry po dnech dával t > 2 u 61 % konfigurací, protože se hodinové události a horizonty až 5 dní překrývají. Proto je výsledek přepočtený.
- Výběr 2011–18, test 2019–26.

## Výsledky

### H1, H4: Je kotva dosažitelná víc než zrcadlová úroveň? Ne.

Dosažení v závislosti na vzdálenosti, průměr přes všechny kotvy (kotva vs zrcadlo, %):

| Vzdálenost | 2h | 1 den | 5 dní |
|---|---|---|---|
| 0,1–0,25 ATR | 27,5 vs 27,8 | 77,0 vs 77,4 | 89,9 vs 90,5 |
| 0,25–0,5 ATR | 8,6 vs 8,7 | 55,1 vs 55,1 | 79,4 vs 80,2 |
| 0,5–1 ATR | 2,0 vs 2,0 | 29,4 vs 29,0 | 62,5 vs 63,4 |
| 1–2 ATR | 0,2 vs 0,2 | 9,1 vs 7,8 | 39,7 vs 36,6 |
| 2–4 ATR | 0 vs 0,1 | 2,5 vs 4,2 | 19,6 vs 15,5 |

- **Po vyvážení driftu** je efekt kotvy: 2h −0,15 p. b. (t −3,0), 3h −0,18 p. b., 12h −0,05, 1 den +0,46 p. b. (t 1,1), 2 dny +1,0 p. b. (t 1,5), 5 dní +1,4 p. b. (t 1,5). Žádná významná výhoda kotvy, v krátkých horizontech dokonce nepatrně záporná.
- Rozdíly v tabulce pro 1–4 ATR a 5 dní jsou z velké části drift: kotva nad cenou má dosažení 73,3 % a kotva pod cenou 61,5 %, zrcadlo 63,0 % a 67,7 %. Efekt kotvy je průměr obou (+1,0 p. b.).
- **Plošné testy:** u dosažení je |t| > 2 u 11,2 % konfigurací (náhoda 5 %), |t| > 3 u 4 z 490. U očekávané hodnoty je |t| > 2 u 5,6 % ze 1 960 (náhoda 5 %). Mezi obdobími 2011–18 a 2019–26 efekty nesouhlasí: korelace 0,09, stejné znaménko 55 %.
- **Nejsilnější náznak:** VAL předchozího dne. Dosažení je o 2,6 až 4,8 p. b. častější při 12h–2d (t 2,4–3,0), stejné znaménko v obou obdobích. Z 490 testů je to málo na důkaz a v očekávané hodnotě to významné není (t < 2,7).
- Podle skupiny kotev (1 den, 0,25–2 ATR) je efekt: VWAP D/W/M −0,1 p. b. (t −0,2), profil POC/VAH/VAL +0,7 p. b. (t 1,5), High/Low dne +0,3 p. b. (t 0,6).

### Protipohyb před cílem (MAE) a stopy

- Medián nepříznivého pohybu před dosažením kotvy (v ATR):

  | Vzdálenost | 1 den | 5 dní |
  |---|---|---|
  | 0,1–0,25 ATR | 0,10 | 0,13 |
  | 0,5–1 ATR | 0,15 | 0,33 |
  | 2–4 ATR | 0,22 | 0,45 |

  90. percentil: u 0,5–1 ATR 0,51 ATR za den a 1,17 ATR za 5 dní.
- **Stop 1 ATR ukončí obchod před dosažením kotvy v 14 % případů** (1 den) a stop 0,5 ATR v 29,5 %. Kotvu pak cena často dosáhne později, jak popisuje zadání. Obchod už ale není otevřený.
- **Očekávaná hodnota (po nákladech):** se stopem je záporná ve všech horizontech (−0,5 až −1,2 b. na obchod). U zrcadla vychází podobně.
- Čistý výsledek obchodu „k kotvě“ bez stopu podle horizontu: 2h −0,53, 12h −0,59, do konce RTH −0,76, 1 den −0,61, 2 dny −0,40, **5 dní +0,15 b.** To se zlepšuje jen díky růstu trhu. Proti zrcadlu je rozdíl +1,8 b. za 5 dní, t 1,1, tedy nevýznamný.

### H5: přes noc vs denní uzavření

- Čistý výsledek na obchod (b.) bez stopu: do konce RTH −0,76, 1 den −0,61, 5 dní +0,15.
- Očekávaná hodnota dělená směrodatnou odchylkou: do konce RTH −0,028, 1 den −0,019, 5 dní +0,003, tedy zhruba nula ve všech horizontech.
- **Držení přes noc nic nepřidává.** Ztráta se u delšího držení zmenšuje stejně u kotvy i u zrcadla (efekt kotvy t ≤ 1,1).

### Seance (Asie / Evropa / USA)

- Efekt kotvy je v každé seanci do ±1,8 p. b. (nevyvážené srovnání). Žádná seance nemá výrazně vyšší dosažitelnost.
- **Kde se cíl dosáhne (1 den):** u událostí v asijské seanci se jen 12,7 % cílů dosáhne ještě v Asii a zbytek později (Evropa, USA). U událostí v Evropě je to 21,8 % a u událostí v USA 63,4 %.
- „Cíl se dosáhne v další seanci“ je tedy zhruba pravidlo, ale protože zrcadlová úroveň se chová stejně, nejde o vlastnost kotvy.

### H3: Impuls → pauza → pokračování (`impulse.py`)

- Impuls = pohyb ≥ 0,3 / 0,5 / 0,75 ATR za 30 minut. Pauza = dalších 60 / 120 / 180 minut v rozsahu ≤ 0,2 / 0,35 ATR. Událost nastane na konci pauzy. Podmínkám vyhovělo 7 kombinací se ≥ 100 událostmi (144 až 4 875 událostí).
- **Závod o první dosažení:** počátek impulsu (reverze) vs prodloužení o stejnou vzdálenost (pokračování). Při náhodné procházce 50 %.
  - Výsledek: 48,7–53,7 %, v průměru 50,1 %.
  - Pokračování v ATR proti stejné době dne: 2h +0,002 (t 0,4), 12h −0,02 (t −0,6), 1 den −0,04 (t −1,2), 2 dny −0,06 (t −1,1).
- Rozdělení podle toho, zda impuls míří k týdennímu VWAP nebo od něj, podle polohy vůči value area minulého týdne, podle vzdálenosti od W-VWAP a podle seance: z 504 testů je |t| > 2 jen 3,2 % (méně než náhoda), |t| > 3 žádný. Mezi obdobími korelace −0,17.
- **Prudký protipohyb následovaný konsolidací tedy nemá předvídatelné pokračování ani návrat.**

## Závěr
1. **Kotvy (VWAP, POC, VAH, VAL, extrémy dne) cenu nepřitahují víc než zrcadlová úroveň na druhé straně.** Efekt je v ±1,5 p. b. a nestabilní mezi obdobími.
2. „Cíl byl nakonec dosažen“ platí stejně dobře u zrcadlové úrovně. Rozhoduje to, zda přežije protipohyb. Při stopu 1 ATR obchod předčasně skončí ve 14 % případů a očekávaná hodnota je záporná.
3. Držení přes noc nebo několik dní zmenšuje ztrátu jen proto, že trh roste. Kotva nic nepřidává.
4. Impuls, pauza a pokračování, ani seance nedávají využitelný vzorec.
5. Jediný náznak je VAL předchozího dne (+2 až +5 p. b. dosažení), nevýznamný na úrovni očekávané hodnoty.
6. Pro hypotézy o footprintu (H2) je potřeba tick export. Připravený modul `research/acsil/ResearchExport.cpp` (nezkompilovaný, bez testu).

**Omezení:**
- Vstup na uzávěrce hodinové svíčky, výplň na přesné úrovni cíle a stopu.
- 1min data, takže pořadí high a low uvnitř minuty neznáme.
- Footprint nebyl testován.
- Hodinové události se překrývají a závěry jsou založené na klastrech po dvou týdnech.

Grafy: `out/charts/`. Tabulky: `out/*.csv`.
