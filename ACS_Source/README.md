# Turtle Breakout Strategy (Sierra Chart ACSIL)

Zjednodušená Turtle-style breakout strategie pro **Nasdaq 100 Futures (NQ), 60minutový graf**.

## Logika

**Vstup:**
- LONG: close nad 200-periodovým MA A close nad předchozím 40-bar maximem
- SHORT: close pod 200-periodovým MA A close pod předchozím 40-bar minimem

**Výstup:**
- Stop loss: 2× ATR(20) — fixní cena nastavená při vstupu (attached stop order)
- Take profit: strukturální — LONG se zavře při close pod aktuálním 40-bar minimem, SHORT se zavře při close nad aktuálním 40-bar maximem

**Position sizing:**
- Riskuje se fixně 2 % equity na obchod
- Počet kontraktů = (equity × risk %) / (stop distance v bodech × hodnota bodu)

## Instalace do Sierra Chart

1. Zkopírujte `TurtleBreakoutStrategy.cpp` do `C:\SierraChart\ACS_Source\`
2. V Sierra Chart: **Analysis → Build Custom Studies DLL** (nebo `File → New/Edit ACS_Source File` a pak Build)
3. Vyberte tento soubor a nechte ho zkompilovat (Build). Po úspěšném buildu se studie objeví v seznamu jako **"Turtle Breakout Strategy"**
4. Otevřete graf **NQ (Nasdaq 100 Futures)** s **60minutovým** intervalem
5. **Analysis → Studies → Add Custom Study** → vyberte "Turtle Breakout Strategy"

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
| Strategy Enabled (Auto Trading) | **No** | musí se ručně přepnout na Yes, aby strategie posílala reálné/simulované objednávky |

## Před živým obchodováním

1. Nejprve otestujte na **Sierra Chart Trade Simulation** účtu (ne na živém účtu)
2. Zkontrolujte, že symbol má správně nastavenou hodnotu bodu (Point Value) v Symbol Settings — používá se pro výpočet velikosti pozice
3. V **Trade → Trade Service Settings** ověřte propojení na váš broker/simulaci
4. Teprve po ověření na simulaci a zpětném testu (Strategy Analyzer / backtest) přepněte "Strategy Enabled" na Yes na reálném/live účtu

## Poznámka

Toto je záměrně jednoduchá verze (žádné časové filtry, trailing stop, denní limity). Podle metodiky "napřed jednoduše, pak přidávat komplexitu po malých krocích" — až bude equity křivka slibná, lze přidat např. trailing stop nebo filtr volatility.
