# Lukacino Multi-System (Sierra Chart ACSIL)

Soubor: `Lukacino_MultiSystem.cpp`. Jedna studie, pět swingových systémů, každý se
dá zapnout nebo vypnout a nastavit. Semi-auto (alerty) i Full auto (příkazy).

## Instalace

1. Zkopírovat `Lukacino_MultiSystem.cpp` do `C:\SierraChart\ACS_Source\`.
2. **Analysis >> Build Custom Studies DLL >> Build**.
3. Graf ES nebo MES (kontinuální, back-adjust), intradenní bary (volume bary nebo
   1 min), časové pásmo **New York**, **Days to Load aspoň 300** (MA200 + ATR).
4. Pro systém Absorption musí mít graf **Bid/Ask Volume** (Chart Settings >> Data).
5. **Add Custom Study >> Lukacino Multi-System**.
6. Full auto: Trade >> Auto Trading Enabled (Global i Chart), nejdřív
   **Trade Simulation Mode** a Replay.

## Jak studie funguje

* Všechny systémy rozhodují **jednou denně v Decision Time** (15:58). „Close dne“
  = close posledního baru, který začal před Decision Time. Dny se zkrácenou seancí
  (poslední bar víc než 15 min před Decision Time) se přeskočí.
* Denní market profile (POC / VAH / VAL) se počítá z barů 09:30–15:58: objem baru
  se rozloží rovnoměrně mezi jeho low a high, value area 70 %.
* Každý systém má **vlastní virtuální pozici**. Na účtu se drží jejich **součet**
  (Sierra má na symbolu jen jednu pozici). Studie pošle vždy jeden příkaz na rozdíl
  mezi cílovou a skutečnou pozicí. Příklad: RSI(2) +1 a Lower Closes +1 → BUY 2.
* **TP a SL systémů hlídá studie** (broker neumí bracket na část pozice). Při
  zásahu pošle market příkaz jen na podíl daného systému.
* **Emergency Stop** je jediný skutečný GTC stop u brokera, na celou pozici.
  Přepočítá se při každé změně pozice.
* Semi-auto: žádné příkazy, jen alert a zpráva v logu s přesným pokynem.

## Inputy

### Hlavní (In 1–7)

| In | Input | Default | Význam |
|---|---|---|---|
| 1 | Trading Enabled | Yes | No = jen počítá a kreslí, žádné nové vstupy |
| 2 | Mode | Semi-auto | Semi-auto = alerty, Full auto = příkazy |
| 3 | Send Orders To Trade Service | No | Yes = živý účet, jen ve Full auto |
| 4 | Decision Time | 15:58 | Denní rozhodnutí všech systémů |
| 5–6 | RTH Start / End | 9:30 / 16:00 | Seance pro profil, high/low, objem, deltu |
| 7 | TP/SL Units | Points | Ticks nebo Points pro všechna TP, SL a VAL Min Depth |

### Pozice a riziko (In 8–18, 86)

| In | Input | Default | Význam |
|---|---|---|---|
| 8 | Sizing Mode | Fixed contracts | Fixed = Size je počet kontraktů. Leverage = Size je páka: kontrakty = účet × Size / hodnota kontraktu |
| 9 | Account Size $ | 50 000 | Pro Leverage a brzdy DD (+ zisky/ztráty studie) |
| 10 | Max Total Contracts | 10 | Strop čisté pozice všech systémů |
| 11 | Opposite Signals | Block | Block = short systém nevstoupí, když je otevřený long (a naopak). Net = pozice se sečtou |
| 12–15 | DD Brake 1 / 2 | −20 % → 0,5 / −30 % → 0,25 | Zmenšení pozic při drawdownu. Nikdy pod 1 kontrakt |
| 16 | Pause New Entries at DD % | 0 (off) | Zastaví nové vstupy na Pause Length dní |
| 86 | Pause Length (days) | 20 | Pak se maximum equity nastaví na aktuální hodnotu a obchoduje se dál |
| 17 | Emergency Stop (× ATR) | 5 | GTC stop celé pozice. 0 = vypnuto |
| 18 | ATR Length | 14 | ATR = průměr denního rozpětí RTH předchozích dní |

### Systémy

Každý systém má na začátku `>>> Název - Enabled` a `Size`, pak své parametry a na
konci stejný **exit blok** (6 inputů).

| Systém | Vstup | Signálový výstup | Parametry (default) |
|---|---|---|---|
| **RSI(2)** (In 19–30) | RSI < práh a close > MA trendu | close > MA výstupu | RSI Length 2, Entry Below 10, Trend MA 200 (0 = off), Exit MA 5 |
| **Lower Closes** (31–42) | N nižších close po sobě | 1. vyšší close / close > MA / close > včerejší high | N 3, Exit Rule 1. vyšší close, Exit MA 5, Trend MA 0 |
| **VAL Swing** (43–56) | close < VAL − Min Depth | close > POC dne vstupu / > VAH / po N dnech | VA 70 %, Depth 0, Exit POC, Fixed 3, Trend MA 0, Draw Yes |
| **Capitulation** (57–68, default OFF) | objem > k × průměr, pokles | close > včerejší high / 1. vyšší close | k 1,6, průměr 20 dní, Require Down Day Yes |
| **Absorption** (69–80, default OFF) | pokles a delta > Min Delta → **short** | po Hold Days dnech | Hold 1, Min Delta 0, Trend Filter Any / nad / pod MA 200 |

**Exit blok (u každého systému):**

| Input | Default | Význam |
|---|---|---|
| Exit Mode | Signal only | 1 Signal only · 2 Signal + Fixed TP/SL · 3 Signal + SL & RRR · 4 Signal + ATR SL & RRR · 5 TP/SL only |
| TP | 40 | Jen Fixed TP/SL a TP/SL only |
| SL | 20 | Fixed TP/SL, SL & RRR, TP/SL only |
| RRR | 2 | TP = SL × RRR (režimy 3 a 4) |
| ATR SL Multiplier | 1,5 | SL = ATR × násobek (režim 4) |
| Max Hold Days | 10 (Capitulation 5, Absorption 0) | Časový stop, 0 = vypnuto |

Pozice končí **prvním** z: signálový výstup (v Decision Time), TP, SL (kdykoli, i
v noci, gap = fill na open), Max Hold, Emergency Stop. Nový vstup stejného systému
nejdřív v Decision Time dalšího dne.

### Zobrazení (In 81–85)

Show Info Panel (Yes/No), Panel Position (4 rohy), Panel Font Size, Alert Number,
Log Detail (Signals only / Everything = i virtuální obchody na historii ve formátu
`TRADE|systém|vstup|výstup|cena vstupu|cena výstupu|směr|kontrakty|důvod`).

## Kontrola inputů (nic se nebije)

* Chybný systém se vypne sám a důvod jde do Message Logu. Ostatní běží dál:
  Size 0, Fixed TP/SL bez TP nebo SL, SL & RRR bez SL nebo RRR, ATR & RRR bez
  násobku, TP/SL only bez Max Hold (pozice by nemusela nikdy skončit).
* Decision Time musí být mezi RTH Start a RTH End, jinak se obchodování vypne.
* Signál bez dostatku historie (MA200, ATR, průměr objemu) se přeskočí.
* Leverage, které vyjde na 0 kontraktů, zapíše do logu varování (typicky účet
  malý pro ES → použít MES nebo vyšší Size).
* Absorption bez Bid/Ask Volume v grafu zapíše varování (delta = 0).

## Bezpečnost

* Příkazy jen při zpracování nových dat (real-time nebo Replay), nikdy při přepočtu
  historie. Pozice, které vznikly na historii, zůstanou virtuální, takže se po
  načtení grafu nevstupuje pozdě.
* Po načtení grafu: pozice na účtu = součet systémů → převezme se. Účet prázdný →
  čeká se na nový signál. Jiná pozice → příkazy se pozastaví a přijde alert
  (srovnat ručně a přepočítat studii).
* Emergency Stop vyplněný u brokera vynuluje všechny systémy.

## Ověření (emulace Replay na ES 07/2016–07/2026)

Emulace `test_harness_ms/` (mini-ACSIL s brokerem: market fill na open, GTC stopy,
netting). Obchody každého systému samostatně proti výzkumu
(`analysis/brainstorm`, `analysis/buy_weakness`), stejné období:

| Systém | Studie | Výzkum | Shodné obchody |
|---|---|---|---|
| RSI(2) | 76 obch, +25,42 b. | 76, +25,42 b. | 100 % |
| Lower Closes | 113, +26,43 b. | 113, +26,43 b. | 100 % |
| Capitulation | 65, +27,05 b. | 65, +27,05 b. | 100 % |
| Absorption | 300, +5,54 b. | 297, +5,59 b. | 100 % (3 navíc na konci dat) |
| VAL Swing | 248, +12,83 b. | 256, +12,03 b. | 94 % (studie nevstupuje v den výstupu) |

* Full auto, všech 5 systémů: 1 131 příkazů, **0 odmítnutých**, P&L brokera
  +10 742 b. = virtuální P&L +10 736 b. (rozdíl = fill na open dalšího ticku).
* Net i Block, Emergency Stop 5 × ATR (2 skutečné stopy za 10 let), všech 5 exit
  módů, Ticks = Points, chybné inputy, Leverage, 40 náhodných načtení grafu
  (žádný pozdní vstup), převzetí a nesouhlas pozice.

Emulace ověřuje logiku, ne kompatibilitu se skutečnou `sierrachart.h`. Tu potvrdí
až Build v Sierře. Chybu z Buildu pošli, opravím ji.

> TP/SL a RRR výstupy jsou k dispozici, ale testy ukázaly, že těmto systémům
> škodí (Lower Closes: Signal only +25 b./obchod, Fixed 40/20 +2,9 b.). Default je
> Signal only.
