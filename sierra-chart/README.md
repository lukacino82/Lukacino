# Previous Session High Breakout – Sierra Chart (ACSIL)

Jednoduchý automatický systém podle pravidel:

| Pravidlo | Implementace |
|---|---|
| Entry | Long, když cena prorazí high předchozí session **zespodu v rámci aktuální session** (předchozí bar téže session zavřel ≤ PSH nebo aktuální bar otevřel ≤ PSH). Gap nad PSH ani pokračování nad PSH není vstup. |
| Stop Loss | Low předchozí (referenční) session |
| Risk/Reward | 1:1 (input `Reward : Risk`) |
| Exit | Target, Stop, nebo konec aktuální session (vypnutelné: `Close Position At End Of Session/Day`) |
| Velikost | 1 kontrakt |
| Limit obchodů | `Max Trades Per Session` (default 1), `Max Trades Per Day` (0 = bez limitu) |

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

Pravidla konzistence:
- V režimu Custom musí být okna **totožná** (předchozí den) nebo **oddělená**. Částečně překrývající se okna (např. 8:00–10:00 a 9:00–16:00) se berou jako chyba – obchodování se vypne a do Message Logu se zapíše hláška.
- Flatten Time mimo obchodní session se ignoruje (pozici pak zavře konec session).
- První, neúplná předchozí session na začátku dat grafu se nepoužije.

Příklady Custom: 9:30–16:00 → 9:30–16:00 (předchozí RTH den), 18:00–9:30 → 9:30–16:00 (overnight → RTH, okna přes půlnoc fungují).

**Direction** – `Long only` (výchozí), `Short only`, `Long + Short`. Short = průraz low předchozí session shora, SL = high předchozí session, TP = vstup − RR × riziko.

Společné: **Reward : Risk**, **Position Size**, **Trading Enabled**.

**Close Position At End Of Session/Day** – `Yes` (výchozí) = pozice se zavře na konci session/dne (Flatten Time, resp. konec bloku). `No` = pozice se drží, dokud ji neukončí Stop nebo Target (i přes noc / do další session); Stop/Target se vždy posílají jako GTC, takže přepnutí volby ani s otevřenou pozicí nenechá pozici bez stopu. Dokud je pozice otevřená, nový obchod se neotevře.

**Omezení počtu obchodů:**
- **Max Trades Per Session** – max. počet obchodů v jedné session (den / okno / blok podle Session Mode). Další obchod v téže session se otevře jen po novém průrazu zespodu (ne hned po zasažení targetu nad PSH).
- **Max Trades Per Day** – celkový denní limit napříč všemi sessions (hodí se hlavně pro Fixed Interval, např. max 3 obchody za den). 0 = bez limitu. Časy jsou v časové zóně grafu.

## Poznámky
- Výchozí `sc.SendOrdersToTradeService = false` → obchoduje se jen v simulaci (Trade Simulation Mode). Pro live účet změň v kódu na `true` – na vlastní riziko.
- Backtest: `Chart >> Replay Chart` nebo `Trade >> Back Test`. Na historii se vstup vyhodnocuje na barech, takže fill ≈ close baru, který prorazil.
