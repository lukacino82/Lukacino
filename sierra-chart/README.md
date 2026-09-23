# Previous Session High Breakout – Sierra Chart (ACSIL)

Jednoduchý automatický systém podle pravidel:

| Pravidlo | Implementace |
|---|---|
| Entry | Long, když cena prorazí high předchozí session (cena v session byla pod PSH, pak `Close > PSH`) |
| Stop Loss | Low aktuální obchodní session v okamžiku vstupu |
| Risk/Reward | 1:1 (input `Reward : Risk`) |
| Exit | Target, Stop, nebo konec dne (`Flatten Time`) |
| Velikost | 1 kontrakt |

Max. 1 obchod za session. Na grafu se kreslí linie Previous Session High, Stop a Target.

## Instalace
1. Zkopíruj `PrevSessionHighBreakout.cpp` do `C:\SierraChart\ACS_Source\`.
2. `Analysis >> Build Custom Studies DLL` → vyber soubor → `Build >> Remote Build` (nebo Local Build).
3. Na grafu: `Analysis >> Studies >> Add Custom Study` → *Previous Session High Breakout*.
4. Zapni `Trade >> Auto Trading Enabled - Global` a `Auto Trading Enabled - Chart`.

## Nastavení (inputs)
- **Reference Session Start/End** – okno, ze kterého se bere high („previous session“). Default 9:30–16:00 = high předchozího RTH dne.
  - Příklad overnight → RTH: Reference 18:00–9:30, Trading 9:30–16:00 (okna přes půlnoc jsou podporována).
- **Trading Session Start/End** – kdy se smí vstupovat a odkud se počítá Session Low.
- **Flatten Time** – čas uzavření pozice na konci dne.
- **Reward : Risk**, **Position Size**.

Časy jsou v časové zóně grafu.

## Poznámky
- Výchozí `sc.SendOrdersToTradeService = false` → obchoduje se jen v simulaci (Trade Simulation Mode). Pro live účet změň v kódu na `true` – na vlastní riziko.
- Backtest: `Chart >> Replay Chart` nebo `Trade >> Back Test`. Na historii se vstup vyhodnocuje na barech, takže fill ≈ close baru, který prorazil.
