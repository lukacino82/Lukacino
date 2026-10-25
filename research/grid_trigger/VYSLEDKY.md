# Grid systémy spouštěné pohybem ceny o X bodů (ES 2011–2026)

**Otázka:** Má dlouhodobou edge systém, který otevře obchod pokaždé, když ES urazí X bodů? Varianty: pokles → long (fade / průměrování), růst → long (momentum / přikupování), shorty, obě strany i náhodný směr. Každý obchod má vlastní TP a SL, včetně malého TP (RRR < 1). Zkoušíme také limit současně otevřených obchodů a filtr přes týdenní a měsíční VWAP. Hypotéza zní: algoritmy na malých timeframech dělají chop a vybírají stopy na obou stranách, a systém, který tomu opakovaně vzdoruje, by mohl mít edge.

## Metodika
- **Data:** ES 1min back-adjusted, 1. 1. 2011 – 25. 9. 2026. Cena se prochází po tickách (0,25 b.), uvnitř minuty v pořadí O → L → H → C u rostoucího baru a O → H → L → C u klesajícího. Simulátor je ověřený nezávislou implementací v Pythonu, shoda je přesná.
- **Trigger (renko logika):** kotva = cena poslední události. Cena na kotvě − X je „pokles“, na kotvě + X „růst“, a kotva se posune. Události nastávají kdykoliv během seance, bez ohledu na to, jak seance začala.
- **Obchod:** vstup za cenu triggeru, SL a TP = SL × RRR, ukončení při prvním dotyku. Na konci Globex dne (16:59 ET) se vše zavře.
- **Limit otevřených obchodů:** 1 / 3 / 10 / neomezeně. Signály nad limit se přeskočí.
- **Velikosti:**
  - v bodech: X 2–30, SL 2–50, RRR 0,25–10;
  - v ATR: denní ATR (X 0,02–0,25, SL 0,03–0,4), hodinové ATR (X 0,1–2,5, SL 0,25–4), týdenní ATR (X 0,01–0,12, SL 0,01–0,15).
- **Náklady:** 0,5 b. na obchod (komise + skluz na stopu). Pro citlivost také 0,25 b.
- **Ověření:** výběr na 2011–18, test na 2019–26. Pro každé pravidlo i náhodný směr jako nulový model. Alfa proti držení 1 kontraktu ES.
- **Celkem 75 360 systémů:**

  | Mřížka | Systémů |
  |---|---|
  | v bodech | 25 920 |
  | v ATR | 3 × 11 520 |
  | s VWAP filtrem | 14 400 |

## A. Pokračuje pohyb, nebo se vrací? (renko, `out/A_renko.csv`)
- Po pohybu o **6–50 b.** jde další pohyb stejným směrem s pravděpodobností **0,503–0,510**. To je náhodná procházka; drobný přebytek odpovídá růstu trhu.
- Malé pohyby **1–4 b.** z 1min dat přesně určit nejde.
  - Hrubší data (5 min) ukazují víc pokračování (X = 4: 0,557 vs 0,509 na 1 min), protože skrývají návraty uvnitř baru.
  - Skutečná ticková hodnota je proto nižší než minutová.
  - V klidných letech 2011–17 vychází X = 2 b. kolem 0,46–0,47, tedy mírný chop.
  - Ani tak by to nestačilo: fade s TP = SL = X vydělá hrubě X·(1 − 2p). U X = 2 a p = 0,46 je to 0,16 b., méně než náklad.

## B. Mřížka v bodech (25 920 systémů, `out/B_grid_body.csv`)
Průměr všech systémů podle pravidla, hrubě před náklady:

| Pravidlo | Hrubě b./obchod | Kladných po nákladu 0,5 | Kladných po nákladu 0,25 |
|---|---|---|---|
| náhodný směr (null) | +0,01 | 1,7 % | 5,6 % |
| fade obě strany (vzdorovat chopu) | −0,13 | 0,2 % | 0,7 % |
| momentum obě strany | +0,13 | 4,3 % | 16 % |
| fade long (pokles → long) | +0,24 | 22 % | 34 % |
| momentum long (růst → long) | +0,48 | 33 % | 55 % |
| long vždy (přikupování + průměrování) | +0,36 | 27 % | 44 % |
| fade short / momentum short | −0,49 / −0,23 | 0 % | 0–2 % |

- **Longy jsou kladné a shorty záporné ve všech variantách.** To je drift ES, ne vlastnost gridu.
- Bez driftu (obě strany) je rozdíl fade vs momentum ±0,13 b. Kalibrace (část F) ukazuje, že i tohle je hlavně artefakt 1min dat.
- **Více současně otevřených obchodů nic nezlepší.** Zisk na obchod zůstává stejný, jen přibude obchodů a nákladů. Medián ročního výsledku „fade obě strany“: max 1 obchod −613 b., max 3 −1 182 b., neomezeně −3 069 b.
- **Tvůj příklad:** pokles 10 b. → long, TP 12 / SL 10, max 1 obchod (`out/G_priklad_X10_TP12_SL10.csv`).

  | Ukazatel | Hodnota |
  |---|---|
  | obchodů ročně | 1 488 |
  | úspěšnost | 42,3 % (bez nákladů je potřeba 45,5 %, s náklady 47,7 %) |
  | hrubě | +0,07 b. na obchod (drift) |
  | čistě | −0,43 b. na obchod = −643 b. ročně ≈ −32 000 USD na 1 kontrakt, t −5,1 |
  | maxDD | −10 600 b. |
  | ziskové roky | 4 ze 16 |

  Stejné nastavení s fade na obě strany dává −0,55 b./obchod, s momentum na obě strany −0,42 b., s náhodným směrem −0,51 b.

## C. Mřížka v ATR (34 560 systémů, `out/C_grid_atr_*.csv`)
- Normalizace přes ATR odstraní vliv toho, že 10 bodů v roce 2011 bylo 0,8 % ceny a dnes je to 0,13 %.
- **Fade obě strany vs momentum obě strany, hrubě b./obchod:**

  | ATR | Fade | Momentum |
  |---|---|---|
  | denní | +0,01 | −0,03 |
  | hodinové | +0,02 | −0,02 |
  | týdenní | −0,01 | +0,01 |

  To je nula.
- **Po nákladech** je kladný 1 systém z 4 320 (D1), 0 ze 4 320 (H1) a 1 ze 4 320 (W1), pokud nepočítáme čisté longy.
- **t > 2** má jen 9 systémů z 34 560, všechno momentum long, tedy drift.

## D. Filtr týdenním / měsíčním VWAP (14 400 systémů, `out/D_vwap_filtr.csv`)
- **Varianty filtru:**
  - „ve směru“: long jen nad VWAP, short jen pod;
  - „proti“: obráceně;
  - týdenní (od neděle 18:00 ET), měsíční a oba zároveň.
- VWAP se počítá jen z předchozích barů. Cena byla nad týdenním VWAP 58 % času a nad měsíčním 64 %.
- **Žádný systém nemá t > 2** (maximum 1,93).
- **Filtr mění hrubý výsledek jen v rámci šumu:**
  - fade long: 0,09–0,33 b. podle filtru vs 0,22 bez filtru;
  - momentum long: 0,25–0,45 vs 0,35.
- **Vyšší RRR nad VWAP nepomáhá.** Long s RRR 10 dává bez filtru +0,63 b., nad měsíčním VWAP +0,53 b., nad týdenním +0,60 b.

## E. Výběr na 2011–18 → test 2019–26 (`out/E_alfa_vyber.csv`)
- **Náhodné systémy vybrané podle 2011–18** (až +0,9 b./obchod) ztratily v letech 2019–26 až −640 b. ročně. Výběr podle minulosti chytá náhodu.
- **Fade long (přikupování poklesů po gridu)** má v testu **významně zápornou alfu** proti držení longu: t −2,3 až −3,3. Je horší než obyčejný buy & hold.
- **Momentum long** má alfu +47 až +159 b. ročně, ale t jen 0,6–1,4, tedy nevýznamná. Beta je 0,2–0,96, takže jde hlavně o expozici na trh.

## F. Pořadí high/low uvnitř minuty (`out/F_cesta_v_minute.csv`, `out/F_cesta_kalibrace.csv`)
- Když pořadí uvnitř baru obrátím, prohodí se fade a momentum: fade obě strany vyjde +0,52 až +0,60 b. místo −0,06 až −0,11 b.
- **Kalibrace:** totéž počítám na 5min barech a porovnám s 1min výsledkem, který pohyb uvnitř 5 minut zná.

  | Pořadí na 5min barech | Fade obě strany, hrubě | Skutečnost z 1min dat |
  |---|---|---|
  | podle směru baru | −0,30 až −0,47 | −0,06 až −0,11 |
  | bližší extrém první | −0,25 až −0,44 | −0,06 až −0,11 |
  | obrácené | +0,17 až +1,01 | −0,06 až −0,11 |

  Obrácené pořadí je tedy výrazně nerealistické.
- S jemnějšími daty se rozdíl fade vs momentum zmenšuje: z 5 min na 1 min zhruba 5×. Na tickách tak bude **0 ± ~0,05 b.**, tedy hluboko pod náklady.
- Pro tickovou přesnost u X a SL ≤ 4 b. by byl potřeba export tickových dat ze Sierra Chart. Na závěru by to nic nezměnilo, protože i nejlepší možný odhad hrubé edge je menší než náklad.

## Závěr
1. **Grid spouštěný pohybem o X bodů nemá na ES dlouhodobou edge** v žádné z 75 360 variant: body i ATR, všechny SL a RRR včetně malého TP, limit 1 / 3 / 10 / neomezeně, s VWAP filtrem i bez něj.
2. **Vzdorovat chopu (fade na obě strany) se nevyplácí.** ES se na škále 6–50 b. chová jako náhodná procházka, takže chop není natolik silný, aby pokryl náklady. Rozdíl fade vs momentum je velikosti šumu (±0,05 b.).
3. **Kladné výsledky mají jen longy, a to je drift trhu.** Proti držení kontraktu nepřinášejí alfu; přikupování poklesů po gridu je dokonce horší než buy & hold.
4. **Víc současných obchodů jen zrychlí ztrátu.** Průměrování dolů i přikupování mají každý obchod se stejnou nulovou hrubou hodnotou a každý platí náklad.
5. **Náklady rozhodují.** Při 1 500–3 000 obchodech ročně stojí náklad 0,5 b. 750–1 500 b. ročně (37–75 tis. USD na kontrakt), a žádná hrubá edge to nevyrovná.

Grafy: `out/charts/` (renko pokračování, hrubý výsledek podle pravidla, heatmapa čistého výsledku, limit obchodů, equity, VWAP filtr, pořadí v baru).
