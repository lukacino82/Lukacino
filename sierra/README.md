# Lukacino Multi-Swing — Sierra Chart studie

ACSIL implementace dvanácti rodin z `swing_lab/results/ES_CORRECTION_ALPHA.html`.
Architektura a seznam Inputů: `swing_lab/SIERRA_ARCHITECTURE.md`.

**Stav: kroky 1 a 3 napsané, krok 2 čeká na tvůj Replay.** Studie počítá signály, vede vlastní
ledger, kreslí do grafu a umí posílat příkazy. Order vrstva vznikla dřív, než proběhl Replay,
takže je napsaná, ale na skutečném účtu **neověřená** — viz *Co order vrstva zaručuje*.

Podrobné nastavení krok za krokem: **`NASTAVENI.md`**.

## Instalace

1. Zkopíruj `Lukacino_MultiSwing.cpp` do `SierraChart\ACS_Source\`.
2. V Sierře: *Analysis → Build Custom Studies DLL → Build*.
3. Zkopíruj `swing_lab/results/swing_presets.csv` do složky *Data Files Folder*
   (*Global Settings → General Settings → Paths*).
4. Otevři **intradenní graf ES nebo MES, 1 minuta**, s celou Globex seancí.
5. *Analysis → Studies → Add Custom Study → Lukacino Multi-Swing*.

## Proč intradenní graf

Studie si denní RTH bary staví sama. Na denním grafu by to nešlo: týdenní a měsíční VWAP
potřebují objemově váženou sigmu, a tu z denních barů spočítat nelze. Měření na tvých datech:
z denních barů má týdenní VWAP mediánovou chybu 1,5 bodu a na pásmu −1,5σ by vzniklo
o 37 % méně signálů. Proto studie agreguje minutová data.

## Kontrola parity

```bash
cd sierra && python run_parity.py
```

Přeloží studii proti `test_stub/sierrachart.h` (minimální náhrada ACSIL API), prožene jí
4,1 milionu reálných minutových barů a porovná výsledek s Pythonem preset po presetu.
Poslední běh, období 2016-06 až 2026-09:

| Kontrola | Výsledek |
|---|---|
| Denní close, IBS | medián i p95 odchylky 0,00000 |
| ATR20, RSI2, ConnorsRSI, sigma VWAP | medián 0,00002, p95 0,00050 |
| Týdenní a měsíční VWAP | medián 0,0026 (přesnost float) |
| Presetů s identickou množinou vstupů | 32 ze 48 |
| Presetů s ≥ 97 % shodou vstupů | 39 ze 48 |
| Obchodů celkem | Python 6 185, studie 6 222 |
| P&L v bodech | Python 77 329, studie 72 948 (94,3 %) |

Studie je záměrně pesimističtější: když se v jedné seanci dotkne SL i TP, počítá **SL první**
na denním rozpětí, zatímco výzkumný engine prochází 30minutové bary. Nižší P&L než backtest
je proto očekávaný směr, ne chyba.

Testovací hlavička záměrně definuje `min`/`max` jako makra stejně jako skutečný `scstructures.h`,
takže se tahle třída chyb odhalí už offline, ne až na build serveru Sierry.

`test_stub/` je pouze testovací náhrada. Není to Sierra Chart a nikdy se nesmí distribuovat
ani použít pro reálné obchodování.

## Co parita neověřuje

Sierra-specifické věci: odesílání příkazů, kreslení, správu seancí samotnou Sierrou a
chování při živých datech. To ověří až Replay podle kroku 2 v `SIERRA_ARCHITECTURE.md`.

## Známé chování

- **Zkrácené seance** (půldny kolem svátků): studie uzavře denní bar až prvním barem další
  seance. Pro živý provoz je přidaná pojistka, která den uzavře, jakmile reálný čas překročí
  konec RTH a nepřišly žádné další bary.
- **Historie** je omezena na 400 denních seancí. Odkazy na dny jsou absolutní čísla seancí,
  takže ořezání historie neposune stav otevřených pozic.
- **Reload presetů** bez restartu: přepni Input *Reload Presets* a zpět.
- **Ledger** se při plném přepočtu grafu přepíše od začátku, ne dopisuje, aby reload grafu
  nezdvojil historii obchodů.
- **Chybějící soubor presetů** se zaloguje **jednou**, ne při každém volání studie. Po zkopírování
  CSV do *Data Files Folder* se načtení znovu spustí přepnutím Inputu *Reload Presets*.
- **Velikost baru:** parita je měřena na 1minutových barech. Na hrubším grafu studie jednou
  zaloguje varování; VWAP sigma a denní rozpětí se tam mírně liší.

## Další kroky

| Krok | Obsah | Stav |
|---|---|---|
| 1 | Feature engine, parser presetů, signály, ledger | hotovo, parita s Pythonem změřená |
| 2 | Sierra Replay 2018–2026, porovnání ledgeru | **čeká na tebe** — postup v `NASTAVENI.md` §8 |
| 3 | Order vrstva: bracket per vstup + srovnání pozice | napsané, na účtu neověřené |
| 4 | Semi-auto na simulovaném účtu, ≥ 50 obchodů | čeká na krok 2 |

Krok 3 předběhl krok 2. Není to důvod ho přeskočit: dokud Replay neukáže, že studie v Sierře
počítá totéž co offline, nemá smysl řešit, jestli správně posílá příkazy.

## Co order vrstva zaručuje

Kniha je 48 presetů, každý s vlastním stopem a targetem. Sierra drží **jednu** pozici na grafu.
Řešení: každý vstup jde jako samostatný příkaz s vlastním bracketem, který spravuje Sierra, a
součet se pak srovnává proti pozici, kterou Sierra hlásí.

| Důvod výstupu | Podíl v referenčním ledgeru | Kdo ho na účtu provede |
|---|---:|---|
| `signal` | 3 477 z 6 504 (53,5 %) | srovnání pozice na konci seance |
| `sl` | 1 415 (21,8 %) | Sierra, připojený stop |
| `tp` | 808 (12,4 %) | Sierra, připojený target |
| `time` | 500 (7,7 %) | srovnání pozice na konci seance |
| `breakeven` | 161 (2,5 %) | **nikdo — stop se v Sierře neposouvá** |
| `trail` | 143 (2,2 %) | **nikdo — stop se v Sierře neposouvá** |

**Známá mezera: posuny stopu se do Sierry nepřenášejí.** Bracket se nastaví při vstupu a už se
nemění, zatímco výzkumný engine u 8 ze 48 presetů stop posouvá (trailing, breakeven). Těch
**304 obchodů ze 6 504, tedy 4,7 %**, na účtu neskončí na posunutém stopu, ale až tržním
příkazem, až je kniha zavře. Pozice přitom zůstává chráněná původním, širším stopem — není to
díra v riziku, ale je to horší výstupní cena a systematicky v neprospěch. Opravit to znamená
posílat `sc.ModifyOrder` na připojený stop; přesné názvy členů ACSIL si musím ověřit v
dokumentaci Sierry, ke které z tohohle kontejneru není přístup (egress policy blokuje
sierrachart.com). Než to půjde ověřit, je to popsané, ne zamlčené.

**Co musí ukázat až Sim účet:** když srovnání pozice odprodá přebytek tržním příkazem, Sierra
zmenší i připojené příkazy zbývajících vstupů. Jestli přitom některý preset zůstane bez stopu,
se z kódu vyčíst nedá — to ukáže krok 4 a je to první věc, kterou tam kontrolovat.
