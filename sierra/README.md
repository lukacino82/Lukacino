# Lukacino Open-X / Range Breakout RRR (Sierra Chart ACSIL)

Soubor: `Lukacino_OpenX_Range_RRR.cpp`. Jedna studie, dva typy vstupu,
čtyři typy výstupu, Semi-auto i Full auto.

## Instalace

1. Zkopírovat `.cpp` do `C:\SierraChart\ACS_Source\`.
2. Sierra: **Analysis >> Build Custom Studies DLL >> Build**.
3. Graf ES (časové pásmo grafu **New York**, časy inputů jsou v čase grafu).
   Add Custom Study >> *Lukacino Open-X Range RRR*.
4. Full auto: **Trade >> Auto Trading Enabled - Global** a **- Chart**
   musí být zapnuté. Nejdřív **Trade Simulation Mode = On** a Replay.

## Inputy

| # | Input | Význam | Default |
|---|---|---|---|
| 0 | Trading Enabled | No = jen kreslí úrovně, žádné signály, alerty ani příkazy | Yes |
| 1 | Mode | Semi-auto = šipky + SL/TP čáry + alert, obchoduješ ručně. Full auto = posílá příkazy | Semi-auto |
| 2 | Send Orders To Trade Service | **Yes = živý účet.** Platí jen ve Full auto | No |
| 3 | Direction | Both / Long only / Short only | Long only |
| 4 | Max Trades Per Day | počet vstupů za den (1–50) | 1 |
| 5 | Position Size | kontrakty na obchod | 1 |
| 6 | Kill Position At Session End | Yes = v čase Flatten Time zavře pozici. No = drží do SL/TP | Yes |
| 7 | Session Start / Open Time | od kdy se bere open (první bar) | 9:30 |
| 8 | Last Entry Time | poslední čas pro nový vstup | 15:00 |
| 9 | Flatten Time | konec seance: kill pozice, konec rozpětí pro ATR | 15:55 |
| 10 | Entry Mode | Open +/- X / Range breakout +/- X | Open |
| 11 | Open +/- X Logic | Breakout: long open+X, short open−X. Fade: long open−X, short open+X | Breakout |
| 12 | Entry Distance X | vzdálenost od open nebo od hrany range | 15 |
| 13–14 | Range Start / End | okno range (pro range vstup a range SL) | 9:30–9:45 |
| 15 | Units | Ticks / Points pro X, TP a SL | Points |
| 16 | Exit Mode | viz tabulka níže | RRR + fixed SL |
| 17 | TP | jen Exit Mode Fixed | 40 |
| 18 | SL | Exit Mode Fixed a RRR + fixed SL | 20 |
| 19 | RRR | TP = SL × RRR (RRR módy) | 2,0 |
| 20 | ATR Length | počet dní pro ATR (RTH rozpětí minulých dní) | 14 |
| 21 | ATR SL Multiplier | SL = ATR × násobek | 0,25 |
| 22 | Range SL Multiplier | SL = výška range × násobek | 1,0 |

### Exit Mode: které inputy se používají

| Exit Mode | SL | TP | Ignoruje se |
|---|---|---|---|
| Fixed TP / SL | SL | TP | RRR, ATR, range násobek |
| RRR + fixed SL | SL | SL × RRR | TP |
| RRR + ATR SL | ATR × násobek | SL × RRR | TP, SL |
| RRR + range SL | výška range × násobek | SL × RRR | TP, SL |

SL a TP se počítají od ceny vstupu a posílají jako offsety od fillu.

### ATR: počítá se samo

ATR ručně nevyplňujete. Studie ho každý den spočítá z dat v grafu:

* **denní rozpětí** = high − low mezi Session Start a Flatten Time (9:30–15:55),
* **ATR** = průměr denních rozpětí za posledních *ATR Length* uzavřených dní
  (dnešek se nepočítá, ATR je známé už na open),
* **SL** = ATR × *ATR SL Multiplier*, **TP** = SL × RRR.

Příklad: ATR(14) = 63 b., násobek 0,25 → SL 15,75 b., RRR 2 → TP 31,5 b.
Ve volatilním období se SL i TP samy zvětší, v klidném zmenší.

Kde vidíte aktuální hodnoty (platí pro každý Exit Mode):
* **v hlavičce studie v grafu** a v okně **Window >> Chart Values**:
  `ATR (points)`, `SL distance (points)`, `TP distance (points)`,
* **v Message Logu** jednou denně po open: `Lukacino: ATR(14) = … | SL = … | TP = …`.

Graf musí mít načteno aspoň *ATR Length* + 1 dní (Chart Settings >>
Days to Load). Do té doby se v módu RRR + ATR SL neobchoduje a log
ukazuje, kolik dní ještě chybí. Když Flatten Time posunete za 16:00,
počítá se do rozpětí i večerní seance a ATR bude o něco větší.

## Konflikty mezi inputy a jak jsou vyřešené

1. **„Open +/- X“ bylo dvojznačné.** Long na open+X (průraz) nebo na
   open−X (nákup poklesu)? Proto input *Open +/- X Logic*. Default je
   Breakout: v testech 2016–2026 byl fade ve všech kombinacích ztrátový.
2. **Send Orders Live vs. Semi-auto.** V Semi-auto se nikdy nic neposílá.
   Live flag se ignoruje a do logu přijde upozornění.
3. **TP / SL / RRR se přebíjely.** Jeden přepínač *Exit Mode*. Každý mód
   bere jen své inputy (tabulka výše), ostatní se ignorují.
4. **Tick vs. bod.** Jeden přepínač *Units* pro X, TP i SL. ATR a range
   jsou vždy v bodech a mají vlastní násobek.
5. **Direction Both + max obchodů.** Max. 1 pozice najednou, žádný
   reversal. Max Trades = počet vstupů za den, long i short dohromady.
   Další vstup až po uzavření pozice a novém protnutí úrovně.
6. **Open +/- X s X = 0.** Long i short by vstoupily hned na open.
   Proto je pro Open mód X ≥ 1 tick povinné. Pro range X = 0 je
   v pořádku (průraz hrany range).
7. **Open +/- X + RRR + range SL.** Range není známý dřív než v Range End.
   Vstupy se proto povolí až po konci range okna.
8. **Časy.** Musí platit Session Start < Last Entry ≤ Flatten Time. Když
   se range používá: Session Start ≤ Range Start < Range End ≤ Last Entry.
9. **Kill = No.** SL/TP se posílají vždy jako GTC, takže nevyprší přes
   noc. Dokud pozice drží, nový vstup (ani další den) nevznikne.
10. **Kill zavírá jen svoji pozici**, tedy tu, kterou otevřela tato
    instance studie. Platí i při Trading Enabled = No: vypnutím
    obchodování nezůstane pozice přes noc. V Semi-auto přijde v Flatten
    Time alert „zavři pozici ručně“.
11. **RRR + ATR SL** začne obchodovat až po N uzavřených dnech v grafu.
    Graf musí mít aspoň ATR Length + 1 dní dat.

Nevalidní kombinace vypne obchodování a zapíše důvod do **Message Logu**
(Window >> Message Log).

## Ochrany proti chybám

* Příkaz se posílá jen na posledním baru (real-time nebo Replay), nikdy
  při přepočtu historie. Na historii jsou jen šipky a čáry.
* **Čerstvé protnutí:** vstup jen tehdy, když cena byla před tím na druhé
  straně úrovně. Po načtení grafu se tedy nevstupuje za cenou, která
  úroveň prorazila už dávno. Signál z historie dnešního dne se počítá do
  Max Trades.
* `MaximumPositionAllowed = Position Size`: vyšší pozici Sierra odmítne.
* Odmítnutý příkaz se zapíše do logu i s důvodem a neopakuje se každý tick.
* Graf začínající uprostřed seance: tento den se neobchoduje (open by
  nebyl skutečný open).

## Chování, které je dobré znát

* Signál = cena (close baru / poslední obchod na živém baru) protne
  úroveň. Vstup je market, takže fill může být o pár ticků za úrovní.
  U volume barů je to velmi blízko.
* Open = open prvního baru, který začíná v Session Start nebo po něm.
* Zkrácené seance (13:00): když po 13:15 nepřijde žádný bar, Kill zavře
  pozici až na prvním baru dalšího dne. V takové dny nastav Flatten Time
  dřív, nebo obchodování vypni.

## Ověření logiky

Studie byla spuštěna na 10 letech ES (volume bary z Excelu) v emulaci
Replay s jednoduchým brokerem (fill na close, SL/TP bracket, SL první
při konfliktu v jednom baru). Náklady 0,5 b./obchod, 1 ES:

| Nastavení | Obchodů | TP / SL / konec dne | Výsledek |
|---|---|---|---|
| Long open+15, SL 20, RRR 2, kill 15:55, vstup do 15:55 | 1 137 | 126 / 408 / 603 | +$45,9k |
| (Python backtest stejných pravidel, fill přesně na úrovni) | 1 181 | 137 / 441 / 603 | +$33,0k |
| Stejné, Kill = No | 971 | 371 / 600 / – | +$117,7k (drift přes noc) |
| Both, Fade | 1 760 | 265 / 739 / 756 | −$74,3k |
| Range 9:30–9:45 průraz, RRR 2 + range SL, Both | 2 555 | 630 / 1 403 / 522 | −$21,8k |

Počty se s nezávislým Python backtestem shodují (rozdíl dělá fill na
close baru místo na úrovni). Všechny přepínače, včetně chybných
kombinací, Semi-auto (jen alerty) a Trading Enabled = No, se chovají
podle popisu. Test načtení grafu uprostřed seance (300 náhodných
okamžiků): ani jednou vstup hned na prvním živém baru.

Emulace je v `test_harness/` (`sierrachart.h` = mini-emulace API,
`main.cpp` = přepočet + Replay po barech). Spuštění:
`g++ -O2 -I. -o h main.cpp && ./h bars.csv 1=1 3=0` (CSV `YYYYMMDD,sekundy,O,H,L,C`,
`index=hodnota` přepíše input, výstup `trades.csv`). Emulace ověřuje logiku,
ne kompatibilitu se skutečnou `sierrachart.h`. Tu potvrdí až Build v Sierra.

**Připomínka z výzkumu:** open ± X ani průraz range samy o sobě hranu
nad náhodný long nemají (viz `reports/open_fade`, `reports/range_atr`).
Zisk long variant pochází z růstu indexu. Studie je nástroj na
automatizaci. Před live nasazením je potřeba 3–6 měsíců sim/paper tradingu
se zmrazenými parametry.
