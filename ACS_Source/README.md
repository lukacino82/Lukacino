# Turtle Breakout Strategy 2.0 (Sierra Chart ACSIL)

Turtle-style breakout strategie pro **Nasdaq 100 Futures (NQ), 60minutový graf**.

## Logika

**Vstup:**
- LONG: close nad 200-periodovým MA A close nad předchozím 40-bar maximem
- SHORT: close pod 200-periodovým MA A close pod předchozím 40-bar minimem

**Výstup:**
- Stop loss: 2× ATR(20) — fixní cena nastavená při vstupu (attached stop order)
- Take profit: strukturální — LONG se zavře při close pod aktuálním 40-bar minimem, SHORT se zavře při close nad aktuálním 40-bar maximem
- **Nové v 2.0 — Breakeven + chandelier ATR trailing:** jakmile cena postoupí ve prospěch pozice o `Breakeven Trigger (x ATR)`, stop se "zaaretuje" na breakeven (průměrná vstupní cena) a dál se posouvá jako chandelier ATR stop (nejvyšší high od vstupu mínus `Chandelier Trailing Multiplier (x ATR)`, zrcadlově pro short). Chrání to nerealizovaný zisk, který by čistě strukturální exit nechal vystavený plnému zvratu 40-bar kanálu.

**Zobrazení stopů v grafu:**
- Fixní 2×ATR stop se pořád posílá jako skutečná attached stop objednávka, takže Sierra Chart automaticky kreslí svou nativní čáru pracující objednávky (`S|Stop|...`) — stejně jako v původní verzi, bez potřeby cokoli nastavovat.
- Trailing/chandelier úroveň není skutečná objednávka v trhu (strategie sama vyšle market exit, jakmile ji cena prolomí) — proto je navíc vykreslená jako vlastní subgraph **"Trailing Stop Level"** (oranžová čára), který ukazuje aktuální efektivní stop po dobu, kdy je pozice otevřená.

**Position sizing:**
- Riskuje se fixně 2 % equity na obchod
- Počet kontraktů = (equity × risk %) / (stop distance v bodech × hodnota bodu)

## Instalace do Sierra Chart

1. Zkopírujte `TurtleBreakoutStrategy.cpp` do `C:\SierraChart\ACS_Source\`
2. V Sierra Chart: **Analysis → Build Custom Studies DLL** (nebo `File → New/Edit ACS_Source File` a pak Build)
3. Vyberte tento soubor a nechte ho zkompilovat (Build). Po úspěšném buildu se studie objeví v seznamu jako **"Turtle Breakout Strategy 2.0"**
4. Otevřete graf **NQ (Nasdaq 100 Futures)** s **60minutovým** intervalem
5. **Analysis → Studies → Add Custom Study** → vyberte "Turtle Breakout Strategy 2.0"

## Nastavení vstupů

| Input | Výchozí | Popis |
|---|---|---|
| Trend MA Length | 200 | perioda trendového MA |
| Breakout Lookback (bars) | 40 | délka Donchian kanálu pro vstup/výstup |
| ATR Length | 20 | perioda ATR pro stop |
| ATR Stop Multiplier | 2.0 | násobič ATR pro stop loss |
| Account Equity ($) | 100000 | kapitál účtu pro výpočet velikosti pozice — **nastavte na reálnou hodnotu** |
| Risk Per Trade (%) | 2.0 | % equity riskované na obchod |
| Max Contracts Per Trade | 50 | strop na velikost pozice |
| Allow Long/Short Trades | Yes | povolení jednotlivých směrů |
| Send Orders To Trade Service (No = internal Trade Simulation Mode) | No | musí odpovídat globálnímu **Trade → Trade Simulation Mode On** — ON (zaškrtnuto, např. při Replay) → nastavte na No; OFF (živý/Sim1 účet) → nastavte na Yes |
| Enable Breakeven + Chandelier Trailing | Yes | zapíná/vypíná nový trailing mechanismus z 2.0 |
| Breakeven Trigger (x ATR) | 1.0 | jak daleko (v násobcích ATR) musí cena postoupit ve prospěch pozice, než se stop zaaretuje na breakeven |
| Chandelier Trailing Multiplier (x ATR) | 3.0 | odstup trailing stopu od nejvyššího high/nejnižšího low od vstupu, po zaaretování breakeven |

Strategie se aktivuje standardním Sierra Chart přepínačem **Trade → Enable Trading for Chart** (studie sama automaticky posílá objednávky, jakmile je trading pro graf zapnutý) — a inputem **Send Orders To Trade Service** nastaveným podle **Trade → Trade Simulation Mode On** (viz tabulka výše).

## Před živým obchodováním

1. Nejprve otestujte na **Sierra Chart Trade Simulation** účtu (ne na živém účtu)
2. Zkontrolujte, že symbol má správně nastavenou hodnotu bodu (Point Value) v Symbol Settings — používá se pro výpočet velikosti pozice
3. V **Trade → Trade Service Settings** ověřte propojení na váš broker/simulaci
4. Teprve po ověření na simulaci a zpětném testu (Strategy Analyzer / backtest) zapněte trading na reálném/live účtu

## Poznámka

Verze 2.0 přidává breakeven + chandelier ATR trailing (viz výše) k původní čisté Turtle logice. Stále chybí časové filtry a denní limity — podle metodiky "napřed jednoduše, pak přidávat komplexitu po malých krocích" je lze přidat později, až bude equity křivka z aktuální verze slibná.
