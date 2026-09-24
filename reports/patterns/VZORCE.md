# Hledání opakujících se vzorců na ES 2016–2026 (s ověřením mimo vzorek)

Data: váš Excel (back-adjustované volume bary ES, 07/2016–07/2026, 2 491
RTH dní). Skripty: `patterns/build.py`, `mine.py`, `report.py`.

## 1. Popisné metriky RTH (09:30–16:00 ET)

| Metrika | Průměr | Medián | 25 % | 75 % | 90 % |
|---|---|---|---|---|---|
| Rozpětí H−L | 45,2 | 36,8 | 20,8 | 59,5 | 87,0 |
| Propad pod open O−L | 23,6 | 13,8 | 5,5 | 32,0 | 58,0 |
| Růst nad open H−O | 21,6 | 13,8 | 6,0 | 30,0 | 49,0 |

* Rozpětí pod průměrem má **60,5 %** dní, v pásmu průměr ±10 % jen
  **11,0 %**, nad průměrem 39,5 %.
* Propad pod open a růst nad open mají stejný medián (13,8 b.). Průměrný
  propad je o 2 b. větší, protože poklesy mají delší chvost.
* **Průměrné rozpětí 30min oken:** 09:30 **17,1 b.** · 10:00 14,7 · 10:30
  12,9 · 11:00 11,7 · 11:30 10,8 · 12:00 10,0 · 12:30 9,5 (minimum) ·
  13:00 10,0 · 13:30 9,7 · 14:00 10,5 · 14:30 10,5 · 15:00 10,8 · 15:30
  **13,9 b.**

## 2. Protokol (proti falešným vzorcům)

* **64 LONG šablon:** vstup (open / limitka open−0,25 ATR / open−0,5 ATR /
  stop open+0,25 ATR) × SL (0,25 / 0,5 ATR) × RRR (1 / 1,5 / 2 / 3) ×
  výstup (16:00 / drží do TP/SL max. 10 dní). Náklady 0,5 b.
* **30 vlastností dne známých na open:** gap, včerejší den, série
  poklesů, poloha close, inside/NR7, široký den, overnight rozpětí a
  poloha open v něm, open vs. včerejší H/L, den v týdnu, přelom měsíce,
  vzdálenost od 20d maxima, režim ATR, minulý týden.
* **1 776 testů.** Hledání jen na **07/2016–12/2021**, ověření na
  zamčených **2022–2026**.
* **Měřítko = přínos nad stejnou šablonou obchodovanou každý den**
  (long bez podmínky). Tím se odečte růst indexu.

## 3. Výsledky

**Nejlepší vzorce z hledání se mimo vzorek rozpadly.** Z top 30 (t 2,2–4,0)
má kladný přínos i v OOS jen **47 %**, tedy stejně jako náhoda. Příklady:

| Vzorec (IS) | t IS | Přínos OOS |
|---|---|---|
| gap nahoru > 0,2 ATR → stop long open+0,25 ATR | 3,5 | záporný |
| přelom měsíce → long, RRR 3:1, drží | 2,9 | záporný |
| open nad včerejším high → long | 2,8 | ≈ 0 |

**Dva kandidáti, kteří přežili (kladní v obou obdobích):**

**A) Nákup poklesu po silném poklesovém dni**
* Podmínka: včera close-close < −0,5 ATR.
* Vstup: limitka open − 0,25 ATR. SL 0,25 ATR, TP 1,5× SL, výstup 16:00.
* 375 obchodů za 10 let, **+$21,8k** (1 ES). Stejná šablona každý den −$8,8k.
* OOS: 185 obchodů, +$11,7k, **t = 0,88**. Přínos nad bázi kladný v 9/11 let.
* Stejná rodina jako swing „close pod VAL“ a RSI(2): **nákup krátkodobé
  slabosti v trhu s dlouhodobým růstem**.

**B) Pondělní long**
* Podmínka: pondělí. Long na open, SL 0,25 ATR, TP 1× SL, drží do TP/SL.
* 463 obchodů, **+$21,6k**. Stejná šablona každý den −$12,4k.
* OOS: 210 obchodů, +$20,0k, **t = 1,65**. Pozor: v období hledání slabý
  (open→close +0,9 b., t 0,6), silný až 2022–2026 (+7,4 b., t 2,9).
  Efekt je závislý na režimu.

## 4. Verdikt a automatizace

* Konkrétní, primitivní a automatizovatelné vzorce existují, ale jsou
  **malé**: +$2k/rok na 1 ES a t mimo vzorek pod 2. Nejsou to stroje na
  alfu. Jsou to kandidáti na forward test.
* Robustní opakující se jev je jen jeden: **kupovat slabost (po poklesu,
  pod hodnotou), ne sílu**. Nejsilnější verze je swing „close pod VAL →
  long do close nad POC“ (+23 b./obchod, t 4,4, `reports/es_orderflow`).
* **Doporučená automatizace (Sierra ACSIL):**
  1. ATR(14) z RTH rozpětí minulých dní, spočítané v 09:30.
  2. Signály A (limitka po poklesovém dni), B (pondělí) a swing pod VAL.
  3. SL/TP v násobcích ATR, velikost pozice = pevné $ riziko / (SL × $50),
     obchodovat přes MES kvůli jemnosti.
  4. 3–6 měsíců paper trading se zmrazenými parametry, pak porovnat se
     zde změřenými čísly.
