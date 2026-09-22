# Lukacino ORB RRR – jednoduchý auto/semi-auto systém pro Sierra Chart

## Logika (Opening Range Breakout)

| Parametr | Pravidlo |
|---|---|
| Range | High/Low prvních **15 min** od otevření (9:30–9:45 NY) |
| Entry LONG | Svíčka **zavře nad** OR High |
| Entry SHORT | Svíčka **zavře pod** OR Low |
| Stop Loss | Opačná strana range (volitelně střed range) |
| Take Profit | Riziko × **RRR** (nastavitelné, default 1:1.5) |
| Exit | SL / TP, jinak **Flatten Time** 15:55 |
| Počet obchodů | Max **1 denně** (první signál vyhrává), vstupy jen do 11:30 |
| Velikost | 1 kontrakt (nastavitelné) |

Volitelné filtry: jen long / jen short, min/max velikost range v ticích.

## Soubory

- `sierra/ORB_RRR.cpp` – ACSIL study pro Sierra Chart (semi-auto i full auto)
- `backtest/orb_backtest.py` – rychlý backtest v Pythonu na exportovaných datech ze Sierry (RRR sweep, in-sample / out-of-sample)

## 1) Instalace do Sierra Chart

1. Zkopíruj `ORB_RRR.cpp` do `C:\SierraChart\ACS_Source\`.
2. `Analysis >> Build Custom Studies DLL` → vyber soubor → **Build >> Remote Build** (nebo Local).
3. Otevři graf (např. ES/MES, **5 min** nebo 1 min), `Analysis >> Studies >> Add Custom Study` → *Lukacino ORB RRR*.
4. Nastav inputy:
   - **Mode**: `Semi-auto` = jen šipky, čáry SL/TP a alert (obchoduješ ručně) / `Full auto` = posílá příkazy.
   - **Session Start Time**: v časové zóně grafu! Pokud máš graf v pražském čase, dej **15:30** (a Last Entry 17:30, Flatten 21:55).
   - **Risk:Reward** – tady měníš RRR.
   - **Send Orders To Trade Service** nech `No` → obchoduje se v simulaci. `Yes` = LIVE účet.
5. Pro full auto zapni `Trade >> Auto Trading Enabled - Global` a `Auto Trading Enabled - Chart`, a měj zapnutý `Trade >> Trade Simulation Mode` (dokud netestuješ live).

Délka svíčky by měla dělit délku range beze zbytku (15 min range → 1, 3, 5 nebo 15 min graf).

## 2) Backtest přímo v Sierra Chart

1. Načti dostatek historie: `Chart >> Chart Settings >> Days to Load` (např. 500).
2. Study v režimu **Full auto**, `Trade Simulation Mode` zapnutý.
3. `Trade >> Back Test` (v novějších verzích *Back Test*/*Replay Back Test*) → zvol **Bar Based Back Test** (rychlé) nebo **Replay Based** (přesnější, tick po ticku), nastav rozsah dat a spusť.
4. Výsledky: `Trade >> Trade Statistics` a `Trade >> Trade Activity Log`.
5. **In-sample / out-of-sample**: optimalizuj RRR jen na starší části (např. 2022–2023), a pak bez změn pusť na novější období (2024–2025). Pokud se výsledek výrazně zhorší, systém je přefitovaný.

## 3) Rychlý backtest v Pythonu (RRR sweep)

Data ze Sierry nahraj do složky `data/` (viz `data/README.md`).

Export dat: `Edit >> Export Bar Data To Text File` (5min graf, RTH).

```bash
cd backtest
# jedno RRR
python orb_backtest.py ES_5min.txt --rrr 1.5
# porovnání více RRR + 30 % dat na konci jako out-of-sample
python orb_backtest.py ES_5min.txt --sweep 0.5 1 1.5 2 3 --oos 0.3
# MES, stop na středu range, jen longy, čas v datech je pražský
python orb_backtest.py MES_5min.txt --point-value 5 --stop mid --direction long \
       --start 15:30 --last-entry 17:30 --flatten 21:55
```

Výstup: počet obchodů, win rate, net P&L v $, průměr na obchod, profit factor a max drawdown – zvlášť pro in-sample, out-of-sample a celek. Poplatky se odečítají (`--commission`, default $4 round-trip). Když svíčka zasáhne SL i TP současně, počítá se konzervativně jako SL.

Seznam obchodů pro kontrolu proti Sierra `Trade Activity Log`:

```bash
python orb_backtest.py ../data/ES_5min.txt --rrr 1.5 --trades trades.csv
```

### Testy logiky

```bash
python -m unittest discover -s backtest/tests -v
```

11 scénářů: long→TP, short→SL, SL+TP ve stejné svíčce (= SL), EOD exit, žádný průraz, průraz po 11:30, jen longy, stop na středu range, filtr velikosti range, max 1 obchod denně, výpočet $ a drawdownu.

> Pozn.: Python backtest vstupuje na close signální svíčky; Sierra v bar-based backtestu plní market příkaz až na dalším ticku/baru, takže čísla se mírně liší. Bereš to jako rychlé třídění nápadů, ne jako finální verdikt.
