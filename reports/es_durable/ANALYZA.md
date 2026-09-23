# Hledání hrany, která může vydržet desítky let

## Princip

Na 8 letech dat nelze *dokázat*, že něco vydrží desítky let. Nový vzorec
nalezený prohledáváním těchto dat by skoro jistě byl přeoptimalizovaný.
Proto jsem otestoval jen primitivní pravidla, která **byla publikovaná
před rokem 2018 a mají za sebou desítky let mimo vzorek**, a to
s **původními parametry, bez ladění**. ES 2019–2026 je pro ně čistý
test mimo vzorek.

Data: ES 1min, back-adjustováno o 33 rolů (neděle po 2. čtvrtku
v březnu, červnu, září a prosinci, celkem 568 bodů carry). Denní RTH
bary. Náklady 0,5 bodu na obchod.

## Výsledky (od 05/2019, po nákladech, body ES)

| Systém | Obchodů | V trhu | Celkem | Na obchod | t | Max DD | Výnos/DD | Kladných let |
|---|---|---|---|---|---|---|---|---|
| Buy & hold | 1 | 100 % | 4 353 | – | 1,98 | −1 206 | 3,6 | 7/8 |
| Noční držení (close→open) | 1 916 | 73 % | 1 794 | 0,9 | 1,29 | −1 218 | 1,5 | 6/8 |
| Noční držení jen nad MA200 | 1 525 | – | 2 336 | 1,5 | 2,32 | −852 | 2,7 | 6/8 |
| **RSI(2) < 10 nad MA200, výstup > MA5** | 72 | **13 %** | 2 082 | **28,9** | **2,64** | **−328** | **6,3** | **7/8** |
| Turn-of-month | 90 | 19 % | 912 | 10,1 | 0,97 | −601 | 1,5 | 4/8 |
| Trend nad MA200 | 25 | 80 % | 3 192 | 128 | 2,02 | −1 221 | 2,6 | 7/8 |

## Kandidát: RSI(2) mean reversion (Connors 2008)

**Pravidla (primitivní):**
* Vstup long na close, když RSI(2) < 10 a close > MA200.
* Výstup na close, když close > MA5.
* Max. 1 pozice. Žádný SL ani TP. Průměrné držení 3,4 dne.

**Proč tomu věřit víc než čemukoli jinému:**
1. **Mimo vzorek:** pravidla i parametry jsou z roku 2008 (testované na
   S&P 1995–2007). Na ES 2019–2026 fungují beze změny.
2. **Plató parametrů:** všech 18 kombinací (práh RSI 5–30 × výstup
   MA3/5/10) je kladných. Výstupy MA3 a MA5 mají t = 2,6–4,7. Nejde
   o šťastný bod.
3. **Nejde o býčí trh:** náhodné vstupy nad MA200 se stejnou délkou
   držení vydělají 6,3 b./obchod, systém 31,8 b. (p = 0,003).
4. **Mechanismus:** placený za poskytování likvidity. Krátkodobé
   výprodeje v indexu jsou z velké části nucené (margin, rebalancing,
   dealer hedging) a v řádu dnů se vrací. Sedí to s intradenní
   mean-reverzí, kterou jsme na ES naměřili.
5. **Náklady jsou zanedbatelné:** hrana ~28 b. na obchod proti nákladům
   0,5 b. U intradenních systémů byla hrana ~0,1–1 b., tedy stejně velká
   jako náklady.

**Exekuce a řízení rizika:**
* Vstup a výstup na open dalšího dne místo close: 27,8 b., t 3,3.
  Stále robustní.
* **Stop-loss škodí:** 3×ATR → t 2,2, 2×ATR → t 1,3. Stop vyhazuje
  pozici v nejlevnějším bodě.
* Časový stop 7 dní: t 3,1, horší nejhorší obchod.
* **Uzavírání na konci seance tuto hranu ničí.** Návrat probíhá přes noc
  a v řádu dnů.
* Nejhorší obchod −149 b. Nejhlubší průběžná ztráta −262 b. (02/2020).
  Max. DD systému −240 až −370 b. podle varianty. Na 1 ES je to
  $12–18k, na **MES $1,2–1,8k**.

**Rizika (proč ani tohle není jistota na desítky let):**
* Denní autokorelace S&P byla do 80. let kladná (momentum). Záporná
  (reverze) je hlavně od ~2000. Hrana tedy závisí na režimu trhu a
  může se zase otočit.
* 65–72 obchodů za 7 let je málo. Jeden roční vzorek může být i
  ztrátový (2022: −137 b.).
* Filtr MA200 chrání před chytáním padajícího nože v medvědím trhu, ale
  ne před bleskovým krachem uvnitř býčího trhu (únor 2020).

## HFT, latenční a statistická arbitráž

* **HFT / latenční arbitráž: pro retail nemá smysl.** Vyžaduje kolokaci
  v CME Aurora, mikrovlnné linky, FPGA a reakce pod mikrosekundu.
  Konkurence jsou Jump, Citadel Securities, Virtu a další. Retailová
  latence (ms až 100 ms) znamená, že byste byl ten, koho „vybírají“.
  Jejich hrana je zlomek ticku na obchod. Přesně ta ~0,1bodová
  mikro-reverze, kterou jsme v ES naměřili, patří jim, protože mají
  náklady blízko nuly.
* **Statistická arbitráž ES vs. SPY / basis / kalendáře:** arbitrážují
  stejné firmy v mikrosekundách, retail nemá šanci.
* **Pomalé „pairs“ (ES vs. NQ v řádu dnů)** nejsou arbitráž, ale rizikový
  obchod. Dají se testovat stejně jako RSI(2), potřebuji ale data NQ.
* **Kde má retail výhodu:** horizont dnů, kde náklady tvoří < 5 % hrany,
  a kapacita, která je pro velké fondy malá.

Skripty: `analysis/research/durable*.py`. Tabulka: `durable_systems.csv`.
