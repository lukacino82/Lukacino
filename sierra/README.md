# Lukacino Multi-Swing — Sierra Chart studie

ACSIL implementace dvanácti rodin z `swing_lab/results/ES_CORRECTION_ALPHA.html`.
Architektura a seznam Inputů: `swing_lab/SIERRA_ARCHITECTURE.md`.

**Stav: krok 1 hotový, krok 2 ověřený na 2016-08 až 2019-12, krok 3 napsaný a na účtu
neověřený.** Studie počítá signály, vede vlastní ledger, kreslí do grafu a umí posílat příkazy.
Replay potvrdil, že v Sierře počítá bod za bod totéž co offline harness (viz *Výsledek Replay*),
ale jen na první třetině období. Order vrstva vznikla dřív, než Replay proběhl — viz
*Co order vrstva zaručuje*.

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
chování při živých datech. Session handling, rollover a bar-po-baru doručování ověřil Replay
(níže); odesílání příkazů na účet zůstává neověřené až do kroku 4.

## Výsledek Replay

Replay z 29. 9. 2026, graf ES 1 minuta, *Days to Load* 400, mód *Signals only*, příkazy vypnuté.
Běh byl zastaven dřív, než dojel do konce: ledger sahá od 2016-08-15 do 2019-12-04, tedy
1 887 obchodů proti 6 504 v referenci za celé období.

`check_replay.py` proti `reference_journal.csv` na překryvu 2016-08-15 … 2019-11-04:

| Kontrola | Výsledek |
|---|---|
| Obchodů | Replay 1 847, offline 1 843 |
| P&L v bodech | Replay 7 932, offline 8 035 (98,7 %) |
| Presetů s identickou množinou vstupů | 43 ze 48 |
| Presetů s ≥ 99 % shodou vstupů | 47 ze 48 |
| Vstupů jen v jedné z knih | 6 (ze 1 847) |
| Entry mimo RTH seanci (sobota nebo neděle) | 0 |

**Všech šest rozdílů leží mezi 2016-08-15 a 2016-08-26**, tedy v prvních devíti seancích grafu,
kde se ConnorsRSI a týdenní/měsíční VWAP ještě nerozběhly — offline harness má natažená data
od 2015-01-01, Replay začíná tam, kam dosáhne *Days to Load*. Po zahození prvních 60 dnů grafu:

| Okno 2016-10-14 … 2019-11-04 | Replay | Offline |
|---|---:|---:|
| Obchodů | 1 726 | 1 726 |
| P&L v bodech | 7 530 | 7 530 |
| Presetů s identickou množinou vstupů | 48 ze 48 | |

Shoda je **úplná, na desetinu bodu**, i v rozdělení důvodů výstupu (`signal` 997, `sl`, `tp`,
`time`, `breakeven` 38, `trail` 38). Sierra tedy nemá vlastní chybu v seancích, rolloveru ani
v pořadí barů; 94,3 % parita proti Pythonu z kroku 1 platí i v Sierře.

Co to neověřuje: období 2020-01 až 2026-09 (covid, 2022, poslední roky) a odesílání příkazů.
Pro zbytek období stačí Replay pustit znovu a nechat dojet — postup je stejný, `NASTAVENI.md` §8.

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
| 2 | Sierra Replay 2018–2026, porovnání ledgeru | 2016-08→2019-12 ověřeno, 100 % shoda po warm-upu; zbytek období dojet |
| 3 | Order vrstva: bracket per vstup + srovnání pozice | napsané, na účtu neověřené |
| 4 | Semi-auto na simulovaném účtu, ≥ 50 obchodů | odblokované, další na řadě |

Krok 4 už na krok 2 nečeká: Replay ukázal, že studie v Sierře počítá totéž co offline, takže
signálová vrstva je hotová a testovat order vrstvu na Sim účtu má smysl. Dojetí Replaye do
2026-09 je na tom nezávislé a dá se pustit vedle.

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
