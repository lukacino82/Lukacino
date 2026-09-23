# ES1: equity, série ztrát a hrana

Vstup: `ES1.txt`, export obchodů ze Sierra Chart (Sim). 138 long obchodů
04/2021–02/2022, 1 ES, SL 10 b. ($500), TP 30 b. ($1 500), jinak výstup 15:56.
V exportu je nulová komise. Pro výsledky „po nákladech“ počítám $25 na
obchod (~$4,5 poplatky + 1 tick skluzu).

## 1. Co systém dělá (rekonstrukce)

Obchodované dny jsou dny, kdy 1min close překoná **high 09:30–09:45**.
Vstup je na open dalšího baru (do 11:30), max. 1 obchod denně. Rekonstrukce
na 1min datech ES sedí se skutečností: **138/138 stejných dní**, vstupní
cena ±0,5 b. u 92 % obchodů, stejný výsledek u 99 %. Díky tomu jde
systém otestovat na 8 letech místo 10 měsíců.

## 2. Výsledky

| | Skutečné obchody 04/21–02/22 | Rekonstrukce 2018–2026 |
|---|---|---|
| obchodů | 138 | 1 400 |
| win-rate | 42,8 % | 36 % |
| hrubě / po nákladech | $14 225 / $10 775 | $61 913 / $26 913 |
| E na obchod po nákladech | $78 (t = 1,23) | $19 (t = 0,95) |
| max. drawdown | −$4 338 | **−$13 325** |
| nejdelší období pod vrcholem | 30 obchodů | **349 obchodů (05/2019–05/2021, 2 roky)** |

Po letech (rekonstrukce, po nákladech): 2018 −$7 438 · 2019 +$6 838 ·
2020 −$4 063 · **2021 +$20 513** · 2022 −$3 438 · 2023 +$12 638 ·
2024 +$8 100 · 2025 −$9 688 · 2026 +$3 450 (do září).

**Testované období (2021) je nejlepší rok z devíti.** Ztrátové jsou 4 roky z 9.

## 3. Série ztrát

| | Skutečné | Rekonstrukce 8 let |
|---|---|---|
| průměrná série ztrát | 2,4 | **2,7** |
| medián | 2 | 2 |
| nejdelší | 6 | **14** |
| 5+ ztrát v řadě | 2× | 50× |
| 8+ ztrát v řadě | 0× | 11× |

* Rozdělení délek sérií přesně odpovídá **náhodě s P(ztráta) = 0,64**
  (geometrické rozdělení, graf `serie_ztrat.png`). Série se neshlukují
  víc, než dává samotná win-rate.
* Při win-rate 36 % připadá na každý zisk průměrně **1,8 ztráty**.
  Průměrná série, kterou musíte ustát, jsou 2–3 ztráty ($1 000–1 500).
* **Co čekat během jednoho roku (~170 obchodů, Monte Carlo):** nejdelší
  série ztrát má medián 10 a v 5 % let 16 a více (−$8 000). Max. drawdown
  má medián −$11 100, v 5 % let −$22 000. Pravděpodobnost ztrátového roku
  po nákladech je **35 %**.

## 4. Má systém hranu?

* **Proti náhodnému longu:** long v náhodném čase 09:45–11:30 se stejnými
  SL/TP vydělá 2018–2026 v průměru 0,26 b./obchod, ES1 0,88 b. Rozdíl je
  0,63 b., **t ≈ 1,3, tedy statisticky neprokazatelný**. Ve vašem období
  2021 bylo p = 0,076.
* Hrubé t = 2,2 za 8 let je z velké části **býčí trh**. Být v ES long
  vydělávalo samo o sobě a ES za období vzrostl ~2,5×.
* **Náklady rozhodují:** hrubě 0,88 b., po 0,5 b. nákladů 0,38 b. Polovinu
  hrany sežerou náklady.
* **Vstup na průrazu je horší než náhodné načasování ve stejné dny**
  (0,88 vs 1,92 b.). To je ale zčásti look-ahead. Test vstupu limitkou na
  retestu high rangu nepomohl (0,92 b.).

**Verdikt:** 10měsíční vzorek (2021) nadhodnocuje. Na 8 letech je to long
ORB se slabou pozitivní hranou, která se po nákladech a po odečtení býčího
driftu nedá prokázat. Drawdown −$13 000 a 2 roky bez nového maxima na
1 ES vyžadují účet aspoň $40–50k. Na účtu kolem $15k je lepší obchodovat
MES (1/10).

## 5. Kam dál

1. **Snížit náklady:** limitní vstup (bez skluzu) a nízká komise. Každý
   ušetřený tick je +$12,5 na obchod, tedy ~+$2 000 ročně.
2. **Režimový filtr s hypotézou:** long ORB jen nad 50denním průměrem
   (neobchodovat long v medvědím trhu 2018/2022). Musí se ověřit
   walk-forward.
3. **Short zrcadlo** (průraz low 15 min) pro medvědí fáze. Symetrie by
   ukázala, jestli je hrana v ORB, nebo jen v driftu trhu.
4. **Forward test na MES** s parametry zmrazenými od dneška.

Skripty: `analysis/research/es1_*.py`. Grafy: `equity_8let.png`,
`equity_skutecne.png`, `serie_ztrat.png`.
