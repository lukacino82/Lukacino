# Order flow, VWAP a market profile na ES: brainstorming a testy

Vstupem jsou jen reálná tržní data, žádné RSI ani klouzavé průměry.
Sierra Chart 1min export obsahuje `BidVolume/AskVolume`, takže:

* **Delta** = objem na asku − objem na bidu (agresivní nákupy − prodeje),
  **CVD** = kumulativní delta od 09:30.
* **VWAP** z reálného objemu (RTH, ±σ pásma) a týdenní VWAP.
* **Market profile** (volume profile RTH, tick 0,25): POC, VAH/VAL (70 %),
  initial balance (09:30–10:30), overnight high/low a overnight delta.

Data: ES 07/2018–09/2026, 2 046 RTH dní, back-adjust o 33 rolů. Náklady
0,5 b. na obchod. **Testovali jsme ~35 variant, takže za signál beru
|t| > 3, ne 2.** Skripty: `analysis/research/orderflow_*.py`,
`profile_swing.py`. Všechna čísla: `hypotezy.csv`.

---

## 1. Brainstorming: jak to uchopit

**Kdo dělá cenu a co vidíme v datech:**
* **VWAP** je benchmark exekuce institucí (VWAP algoritmy, hodnocení
  tradera). Instituce nakupují pod VWAP a prodávají nad ním, takže VWAP
  by měl fungovat jako magnet a support/rezistence.
* **Value area / POC** ukazuje, kde trh včera našel „férovou cenu“.
  Dalton: cena mimo hodnotu buď hledá nový obchod (přijetí →
  trend), nebo je odmítnuta (návrat do hodnoty, 80% pravidlo).
* **Delta** měří agresi. Když agrese nepohne cenou, je tam pasivní
  protistrana (absorpce). Když cena dělá nové high bez nákupní agrese,
  je pohyb „prázdný“ (divergence).
* **Initial balance** je rozsah, na kterém se shodnou první hráči.
  Jeho rozšíření ukazuje, že vstoupil dlouhodobý kapitál.

**Hypotézy, které jsme testovali (intraday):**

| # | Hypotéza | Logika |
|---|---|---|
| H1 | Open nad VAH → long, pod VAL → short | přijetí mimo hodnotu = trend |
| H2 | 80% pravidlo: open mimo VA, 30min close zpět uvnitř → druhá hrana VA | odmítnutí mimo hodnotu |
| H3 | Včerejší POC jako magnet | férová cena přitahuje |
| H4 | Průraz IB + souhlas CVD | agrese potvrzuje průraz |
| H5 | Úzký IB → rozšíření dne | komprese → expanze |
| H6 | Strana VWAP v 10:30/11:30 → směr zbytku dne | kontrola institucí |
| H7 | 1. pullback na VWAP ve směru jeho sklonu | vstup s institucemi |
| H8 | Fade ±2σ / 2,5σ od VWAP | přetažení od férové ceny |
| H9 | Nové high/low bez potvrzení CVD → fade | prázdný pohyb |
| H10 | Absorpce: extrémní delta baru, cena jde proti | pasivní protistrana |
| H11 | Cena i CVD stejným směrem v 1. půlhodině → pokračování | souhlas agrese a ceny |

**Swing / poziční:**

| # | Hypotéza |
|---|---|
| S1 | Divergence denní delty (růst + záporná delta, pokles + kladná delta) |
| S2 | Migrace value area (2 dny výš / níž) |
| S3 | Close dne vůči VA (přijetí nad VAH / pod VAL) |
| S4 | Overnight delta → směr RTH |
| S5 | Close vs. týdenní VWAP |

---

## 2. Výsledky

### Intraday: nic nepřekročilo |t| > 3

| Hypotéza | Obchodů | b./obchod | t | Závěr |
|---|---|---|---|---|
| H1 open nad VAH → long | 801 | −1,3 | −1,0 | přijetí mimo hodnotu nepokračuje |
| H1 open pod VAL → short | 557 | −2,7 | −1,4 | dtto |
| H2 80% pravidlo | 455 | 0,0 R | 0,1 | **na ES neplatí** (52 % win při symetrickém SL) |
| H3 POC magnet | 1 913 | P = 0,50 vs zrcadlo 0,46 | 2,4 | slabý magnet, na obchod nestačí |
| H4 IB průraz, CVD souhlasí | 1 508 | +0,2 | 0,3 | nic |
| **H4 IB průraz, CVD nesouhlasí** | 362 | **−4,3** | **−2,7** | **delta funguje jako filtr špatných průrazů** |
| H5 úzký IB | – | den se rozšíří 2,7× IB vs 1,7× u širokého | – | užitečné pro TP, ne pro směr |
| H6 strana VWAP 10:30 | 2 046 | −0,6 | −0,8 | VWAP nedává směr dne |
| H7 pullback na VWAP | 1 729 | 0,0 | 0,0 | nic |
| **H8 fade 2σ, 60 min** | 1 647 | **−1,0** | **−2,8** | **za 2σ trh pokračuje, nefadovat** |
| H9 CVD divergence na high/low | 1 625 | −0,5 | −0,6 | divergence nefunguje |
| H10 absorpce | 46 | +1,5 | 0,5 | vzácné, neprůkazné |
| H11 cena + CVD 1. půlhodina | 1 484 | +0,5 | 0,5 | nic |

**Proč:** ES je nejlikvidnější futures na světě. Informace z delty a VWAP
se do ceny dostane během sekund až minut, a to vybírá HFT. Po 5min baru
a nákladech 0,5 b. už nic nezbývá. Delta ale **informaci nese**
(H4 „nesouhlasí“ −4,3 b.). Nejlépe se hodí jako *veto*: nevstupovat do
průrazu, který agrese nepotvrzuje.

### Swing: nákup pod hodnotou funguje

| Hypotéza | Obchodů | b./obchod | t | Kladné roky |
|---|---|---|---|---|
| **S3 close pod VAL → long 1 den** | 348 | **+9,2** | **3,0** | **8/9** |
| S2 2 dny VA níž → long 3 dny | 316 | +12,9 | 2,7 | 6/9 |
| S5 close pod týdenním VWAP → long 1 den | 841 | +3,5 | 1,8 | 8/9 |
| S1 pokles + kladná delta → long 3 dny | 296 | +5,0 | 0,9 | 5/9 |
| S3 close nad VAH → long (přijetí) | 420 | −0,8 | −0,3 | – |
| S4 overnight delta → RTH směr | 2 046 | −0,5 | −0,6 | – |
| *benchmark: buy & hold 1 den* | 2 045 | +1,7 | 1,6 | 7/9 |

---

## 3. Kandidát: „Pod hodnotou kupuj“ (čistý market profile)

**Pravidla:**
1. Na konci RTH (16:00 ET): pokud **close < VAL dnešního profilu** → long
   (na close nebo MOC).
2. Výstup: první close **nad POC dne vstupu**, nejpozději po 10 dnech.
3. Max. 1 pozice. Žádný SL (viz níže), žádný indikátor.

**Robustnost:**
* Pevné držení 1/2/3/5/10 dní: **t = 3,0 / 3,3 / 4,0 / 3,7 / 4,9**.
  Vždy výrazně nad buy & hold se stejnou délkou (např. 3 dny +18,4 vs
  +6,5 b.).
* Výstup nad POC: **210 obchodů, +23,4 b./obchod, t 4,4, win 83 %**,
  průměrně 4,2 dne, max. DD −459 b., kladných 7/9 let.
* Náhodné dny se stejným držením: p = 0,0018.
* Hloubka pod VAL nehraje roli (všechny tři pásma kladná). Nejde
  o bod optimalizace.
* **Asymetrie:** close nad VAH → short nefunguje (−0,2 b.). Hrana je
  nákup slabosti v trhu s kladným dlouhodobým driftem (poskytnutí
  likvidity + rizikové prémium). Je to stejný jev, jaký jsme našli
  u RSI(2), tady ale bez zpožděného indikátoru.

**Rizika:**
* Nejhorší obchod bez stopu −379 b. (krachový týden). Stopy
  mean-reversion hranu ničí (ověřeno u RSI2), proto riziko řídit
  **velikostí pozice** (MES), ne stopem. Případně jen katastrofický stop
  jako pojistka.
* 210 obchodů za 8 let. Robustnost na desítky let nelze z těchto dat
  dokázat.

---

## 4. Co dál

1. **Pouze pro Sierra Chart:** ACSIL studie „Pod hodnotou kupuj“
   (profil z RTH, signál na 15:59, výstup nad POC) + paper trading.
2. **Delta jako veto:** do stávajících průrazových systémů (ES1) přidat
   pravidlo „nevstupuj, když CVD nesouhlasí se směrem průrazu“ a změřit
   walk-forward.
3. **Test na NQ/RTY/YM** beze změny pravidel. Nejsilnější důkaz.
4. **Nápady, které stojí za otestování s tick daty** (1min bary na ně
   nestačí): footprint imbalance (3:1 na více cenových úrovních),
   stacked imbalances, velké lotové obchody (block trades), iceberg
   detekce na bid/ask, rychlost tape (trades/s) při testu úrovně.
