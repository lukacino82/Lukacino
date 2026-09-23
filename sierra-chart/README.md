# Previous Session High Breakout – Sierra Chart (ACSIL)

Jednoduchý automatický systém podle pravidel:

| Pravidlo | Implementace |
|---|---|
| Entry | Long, když cena prorazí high předchozí session (cena v session byla pod PSH, pak `Close > PSH`) |
| Stop Loss | Low předchozí (referenční) session |
| Risk/Reward | 1:1 (input `Reward : Risk`) |
| Exit | Target, Stop, nebo konec aktuální session |
| Velikost | 1 kontrakt, max. 1 obchod za session |

Na grafu se kreslí linie Previous Session High, Previous Session Low (= stop) a Target.

## Instalace
1. Zkopíruj `PrevSessionHighBreakout.cpp` do `C:\SierraChart\ACS_Source\`.
2. `Analysis >> Build Custom Studies DLL` → vyber soubor → `Build >> Remote Build` (nebo Local Build).
3. Na grafu: `Analysis >> Studies >> Add Custom Study` → *Previous Session High Breakout*.
4. Zapni `Trade >> Auto Trading Enabled - Global` a `Auto Trading Enabled - Chart`.

## Nastavení (inputs)
**Session Mode** – vždy platí právě jeden režim, režimy se nemíchají. Určuje zároveň, co je předchozí session, kdy se obchoduje a kdy se pozice zavírá. Inputy s prefixem jiného režimu se ignorují.

| Session Mode | Předchozí session (high/low) | Obchoduje se | Exit | Používané inputy |
|---|---|---|---|---|
| Custom Time Window | okno `[Custom] Previous Session Start–End` | okno `[Custom] Trading Session Start–End` | Flatten Time / konec okna | `[Custom]`, Flatten Time |
| Daily (Previous Day) | celý předchozí obchodní den (Session Times grafu) | aktuální obchodní den | Flatten Time / konec dne | Flatten Time |
| Fixed Interval (minutes) | předchozí blok N minut (např. 60 = předchozí hodina) | aktuální blok | konec bloku | `[Interval] Interval Length` |

Příklady Custom: 9:30–16:00 → 9:30–16:00 (předchozí RTH den), 18:00–9:30 → 9:30–16:00 (overnight → RTH, okna přes půlnoc fungují).

Společné: **Reward : Risk**, **Position Size**, **Trading Enabled**. Časy jsou v časové zóně grafu.

## Poznámky
- Výchozí `sc.SendOrdersToTradeService = false` → obchoduje se jen v simulaci (Trade Simulation Mode). Pro live účet změň v kódu na `true` – na vlastní riziko.
- Backtest: `Chart >> Replay Chart` nebo `Trade >> Back Test`. Na historii se vstup vyhodnocuje na barech, takže fill ≈ close baru, který prorazil.
