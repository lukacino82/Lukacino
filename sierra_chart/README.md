# Lukacino Auto Trader — Sierra Chart (ACSIL)

Primitivní semi / full-auto trading study s bracket ordery (TP + SL) a trailing stopem
v režimu **group** nebo **per position**.

Soubor: `LukacinoAutoTrader.cpp`

---

## 1. Instalace

1. Soubor `LukacinoAutoTrader.cpp` zkopíruj do adresáře Sierra Chart `Data`
   (typicky `C:\SierraChart\Data\`).
2. V Sierra Chart: **Analysis → Build Custom Studies from Source Code** → vyber soubor
   → *Build*. V okně se nesmí objevit error.
3. Na chart: **Chart → Studies → Add Custom Study →** `Lukacino Auto Trader`.
4. Aby study mohla obchodovat, musí být zapnuto:
   - **Trade → Auto Trading Enabled (Global)**
   - **Trade → Auto Trading Enabled for Chart**
   - a na začátku taky **Trade → Trade Simulation Mode On** (viz Bezpečnost níže)

### Tlačítka na Control Baru (volitelné)
Study registruje tři ACS buttony: `LCN Buy`, `LCN Sell`, `LCN Flat`.
Přidej je přes **Chart → Chart Settings → ... → Control Bar** (ACS Tool Bar buttony 1–3),
nebo použij input `06. Manual trigger`, který funguje stejně a sám se resetuje na `Off`.

Kdyby build hlásil chybu na `SetCustomStudyControlBarButtonText`, nastav na začátku
souboru `#define LCN_USE_ACS_BUTTONS 0` a používej input `06. Manual trigger`.

---

## 2. Logika systému

### Stav
Study si drží interní tabulku max **20 „slotů"** — jeden slot = jeden obchod.
Každý vstup se posílá jako samostatný market order s vlastním attached OCO bracketem
(TP limit + SL stop). Díky tomu lze trailovat každý obchod samostatně, i když Sierra
Chart drží jednu netto pozici na symbol.

### Smyčka (každý tick, jen na posledním baru)

| # | Krok | Co se děje |
|---|------|-----------|
| 1 | **Sync slotů** | Dohledání fillu vstupu, dohledání attached orderů podle `ParentInternalOrderID`. Detekce uzavření (TP nebo SL fillnutý / oba ordery zrušené) → výpočet realizovaného P/L, uvolnění slotu, zápis do Message Logu. |
| 2 | **Kill switch** | Manuální input, nebo automatika při dosažení denní ztráty → `FlattenAndCancelAllOrders()` + blok dalších vstupů. |
| 3 | **Trailing** | Group nebo per-position, posun stop orderu přes `ModifyOrder()`. |
| 4 | **Signál** | Manuální trigger (tlačítko / input) → volitelně externí study subgraph → full-auto re-entry. |
| 5 | **Vstup** | Výpočet SL/TP offsetu, `BuyEntry()` / `SellEntry()` s attached bracketem. |
| 6 | **Kreslení** | Entry / TP / SL / Trail linky s labely + statusový text nad posledním barem. |

### Režimy

**Semi auto** — jeden obchod na jeden signál. Když se obchod uzavře, nic se nestane,
čeká se na další signál.

**Full auto** — po uzavření obchodu si script zapamatuje směr, počká
`25. Full auto re-entry delay` sekund a otevře stejný obchod znovu. Opakuje,
dokud nenarazí na `17. Max trades per day`, kill switch, nebo dokud nevypneš
`01. Trading enabled`.

**Start sekvence** — input `29. Open initial position now` = Yes otevře první
pozici okamžitě. Ve full auto režimu tím rozjedeš celý cyklus: od té chvíle se
po každém uzavření otevírá další obchod sám.

Funguje stejně jako v Pyramiding Pro System — **edge detekce přepnutí No → Yes**
proti uložené předchozí hodnotě. Input se sám neresetuje, přepneš ho zpátky na
No ručně. Odpálí jen když není nic otevřeného; v režimu `Both` je **blokovaný**
(není jednoznačné, kterým směrem) a zapíše se to do Message Logu — pro short
použij `02. Mode = Short only`, tlačítko `LCN Sell` nebo input
`06. Manual trigger`.

Stejnou edge detekci používá i input `06. Manual trigger` — po vstupu zůstane
na `Buy` / `Sell`, pro další manuální vstup ho přepni zpátky na `Off`.
Po načtení study si script nejdřív jen zapamatuje stav přepínačů a neodpálí nic
— chart s inputem 29 nechaným na Yes tedy po reloadu sám neobchoduje.

### TP / SL

```
SL mode = Fixed  →  SL = hodnota z inputu 09 (ticky nebo body)
SL mode = ATR    →  SL = ATR(period) × multiplier

TP mode = Fixed  →  TP = hodnota z inputu 13
TP mode = RRR    →  TP = SL × RRR
```
Oba offsety se zaokrouhlují na násobek `TickSize`, minimum 1 tick.

### Trailing stop

Aktivuje se, až profit obchodu dosáhne `20. Trail trigger`. Pak:
```
nový stop = aktuální cena ∓ 21. Trail distance
```
Stop se posouvá **jen v příznivém směru** a jen když je posun alespoň
`22. Trail min step` (aby se neposílalo `ModifyOrder` na každý tick).

- **Per position** — každý obchod trailuje od svého entry, nezávisle na ostatních.
- **Group** — jedna společná hladina počítaná z průměrné ceny netto pozice
  (`AveragePrice`); jakmile se posune, zapíše se **všem** otevřeným obchodům
  stejného směru.

### Kill switch

- Input `23. KILL SWITCH` = Yes → okamžitě flatten + cancel all + blok vstupů.
- `24. Daily loss limit` > 0 → když **realizované + otevřené** P/L dne klesne na
  `-limit`, kill switch zaskočí sám (latch).
- **Reset latche:** přepni input `23` na Yes a zpátky na No, nebo se latch sám
  uvolní s novým obchodním dnem.

### Ostatní pravidla

- Obchody **proti** otevřené pozici se nezadávají (žádné reversals).
- `16. Max concurrent trades` = kolik obchodů může být otevřeno současně
  (scale-in). `sc.MaximumPositionAllowed` se automaticky nastaví na
  `max concurrent × position size`.
- `17. Max trades per day` = počet **vstupů** za obchodní den, 0 = bez limitu.
- Během full recalculation (přepočet historie) se neobchoduje.
- `01. Trading enabled` = No zablokuje **nové** vstupy, ale otevřené obchody se
  dál spravují a trailují — záměrně, aby pozice nezůstala bez správy.

---

## 3. Inputy

| # | Input | Default | Poznámka |
|---|-------|---------|----------|
| 01 | Trading enabled | No | Blokuje jen nové vstupy |
| 02 | Mode | Both | Long only / Short only / Both |
| 03 | Auto mode | Semi auto | Semi / Full auto |
| 04 | Units for TP / SL / Trail | Ticks | Ticks / Points |
| 05 | Entry source | Manual only | Manual / Study signal / oboje |
| 06 | Manual trigger | Off | Buy / Sell, sám se resetuje |
| 07 | Signal study subgraph | — | `>0` = long, `<0` = short, edge z nuly |
| 08 | SL mode | Fixed | Fixed / ATR |
| 09 | SL fixed | 20 | v jednotkách z inputu 04 |
| 10 | ATR period | 14 | Wilders |
| 11 | ATR multiplier | 1.5 | pro SL |
| 12 | TP mode | RRR x SL | Fixed / RRR |
| 13 | TP fixed | 40 | v jednotkách z inputu 04 |
| 14 | RRR | 2.0 | TP = SL × RRR |
| 15 | Position size | 1 | kontraktů na obchod |
| 16 | Max concurrent trades | 1 | max 20 |
| 17 | Max trades per day | 10 | 0 = unlimited |
| 18 | Trailing stop enabled | Yes | |
| 19 | Trailing mode | Per position | Group / Per position |
| 20 | Trail trigger | 12 | profit, od kterého se trailing zapne |
| 21 | Trail distance | 8 | odstup stopu od ceny |
| 22 | Trail min step | 2 | minimální posun stopu |
| 23 | KILL SWITCH | No | flatten + block |
| 24 | Daily loss limit | 0 | v currency, 0 = off |
| 25 | Full auto re-entry delay | 5 | sekundy |
| 26 | Send orders to trade service | Yes | No = interní simulace study |
| 27 | Draw entry / TP / SL / trail | Yes | |
| 28 | Log events to Message Log | Yes | |
| 29 | Open initial position now | No | ruční odpal první pozice, **přepni zpátky na No ručně** |
| 30 | Show status text | Yes | vypnutí statusového textu na chartu |
| 31 | Status text color | světle šedá | barva statusového textu (např. černá na bílý chart) |
| 32 | Status text font size | 10 | 5–40 |

---

## 4. Co je vidět na chartu

- **ENTRY #n** — šedá tečkovaná linka na entry ceně (`L` / `S` = směr)
- **TP #n** — zelená linka
- **SL #n** — červená linka (původní stop)
- **TRAIL #n** — oranžová linka, jakmile se stop odlepí od původní úrovně
  (stejná linka, mění barvu a posouvá se)
- **Statusový text** nad posledním barem:
  `LCN | ON | FULL AUTO | BOTH | open 2/3 | today 4/10 | P/L -125.00 | trail: PER-POSITION`
  Vypíná se inputem `30`, barva a velikost jdou nastavit inputy `31` a `32`.
  Při aktivním kill switchi se text vždy přepne na červenou, bez ohledu na input 31.

Nativní order lines Sierra Chart (fill markery, pending ordery) zůstávají zapnuté
nezávisle na tomhle — zapíná se v **Chart Settings → Trading**.

---

## 5. Bezpečnost — přečti před prvním spuštěním

1. **Začni v Trade Simulation Mode** (`Trade → Trade Simulation Mode On`).
   Logika je stejná, jen se neposílá nic brokerovi.
2. `01. Trading enabled` nech na **No**, dokud si neprojdeš všechny inputy.
3. Ve full auto režimu **vždy** nastav `17. Max trades per day` a
   `24. Daily loss limit`. Full auto jinak jede dokud nevypne elektřina.
4. Script **nemá time filter** — neomezuje obchodování na session. Pokud to chceš,
   je to doplnění pár řádků, řekni.
5. Realizované P/L se počítá interně z fill cen (`AvgFillPrice`) a
   `CurrencyValuePerTick`, nezahrnuje komise. Pro denní loss limit to stačí,
   pro reporting použij Sierra Chart Trade Activity Log.
6. Při ručním zavření pozice mimo script (např. z Trade DOM) se slot uvolní, ale
   exit cena se dopočítá z poslední ceny — P/L je pak přibližné.

---

## 6. Build

Ověřeno proti remote build serveru Sierra Chart (`build.sierrachart.com`, 64-bit).

Opravy po prvním buildu:

| Chyba | Oprava |
|-------|--------|
| `MaintainTradeStatsAndTradesData` neexistuje | → `MaintainTradeStatisticsAndTradesData` |
| `sc.GetTradingDayDate()` vrací `int`, ne `SCDateTime` | zrušeno volání `.GetDate()` |
| `sc.FormatString()` nejde volat se string literálem | všech 11 výskytů přepsáno na `SCString` + `.Format()` |

Po prvním buildu navíc převzato z `PyramidSystem.cpp` / `CascadePyramidSystem.cpp`:
edge detekce triggerů místo zápisu do inputu, a grace counter po fillu vstupu
(10 updatů), než se bracket ordery objeví v order listu.

Pokud by si build stěžoval na `sc.SetCustomStudyControlBarButtonText`
(ACS tlačítka), nastav na začátku souboru `#define LCN_USE_ACS_BUTTONS 0`
a používej input `06. Manual trigger`.

---

## 7. Co tu záměrně není

- time / session filter (obchoduje kdykoli)
- break-even krok a stupňovitý trailing po R násobcích
- breakout / limit vstupy (vstupuje se market orderem)
- vlastní signální logika (indikátor) — napojuje se zvenku přes input 07
- max consecutive losses

Všechno je to doplnitelné, ale do „primitivní první verze" to nepatří.
