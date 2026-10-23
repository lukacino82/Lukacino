# BCL (big cycle lines, Forex Rebel) – logika čar a test na S&P 500 2008–2026

Kód:
- `bcl_data.py` – data;
- `bcl_test.py` – všechny varianty TP/SL;
- `w1_oos.py` – předem stanovená hypotéza.

Výsledky jsou v `out/`.

## 1. Jak indikátor počítá čáry
- **Zdroj:** excel kurzu „ciara-MC“ (Forex Rebel). Heslo bylo v uživatelově poznámce. Indikátory .ex4 jsou zašifrované.
- **Excel:** cyklus = pohyb ceny, který plně zapákovaný účet (marže = celý účet) srazí na stop-out 30 %:
  - **cyklus = 0,7 × cena / páka**;
  - EURUSD, páka 25: 0,028 × 1,058 = 296 pipů.
- **Indikátor BCL:** parametr REBEL_POSUN_KONSTANTA.
  - 70 → cyklus 2,8028 % ceny (graf D1, box 2138 = 213,8 bodu);
  - 700 → 28,028 % (W1, box 21369).
- **Červené čáry** jsou geometrické: každá nižší = vyšší × (1 − c). To je úroveň margin callu longu otevřeného na vyšší čáře.
- **Mezičáry** jsou lineární čtvrtiny cyklu: modrá 3/4, žlutá 1/2, fialová 1/4.
- **Shoda s grafy:** rekonstrukce sedí na všechny popisky uživatelových grafů s přesností ±0,03 bodu.
  - W1: R0 = 2908,44, krok ×1,389430.
  - D1: R0 = 7219,03, krok ×1,028836.
- **Ukotvení** (výchozí cena) z kódu známé není. Je převzaté z grafů.
- **Obchodní plán kurzu:** obchodovat celý cyklus, TP minimálně 1 cyklus, při silném trendu přikupovat.

## 2. Data
- **2018-07 – 2026-09:** 1min ES převedené přesně na cenu brokera US500Cash.
  - Denní kalibrace na D1 brokera; čas serveru = New York + 7 h.
  - Kontrola proti H1 brokera: medián chyby 0,75 bodu.
- **2008-05 – 2018-07:** ES2008 (back-adjusted).
  - Raw ceny se rekonstruují vrácením roll gapů (model carry: LIBOR − dividendový výnos).
  - Převod na cash přes fair value.
  - Korekce na 17 známých uzavíracích hodnot S&P 500.
  - Proti datům brokera 2017-09 – 2018-07: medián rozdílu 1,8 bodu, IQR ±4 body.
  - Stačí to pro W1 čáry a červené D1 čáry. Na D1 čtvrtinách (≈ 7–19 bodů v tehdejších cenách) je to na hraně.

## 3. Metodika
- **Událost:** první dotek čáry poté, co cena byla aspoň 1/8 cyklu daleko. Vstup přesně na čáře.
- **Výsledek:** 5min bary; co přijde dřív, odraz zpět, nebo průraz skrz o 1/8 – 2 cykly. Horizont 250 dní (W1), resp. 60 dní (D1).
- **Varianty TP/SL:**
  - fade: TP zpět, SL skrz;
  - breakout: TP skrz, SL zpět.
- **Rozsah:** 49 kombinací × 2 směry × 4 typy čar (červené, 1/2, 1/4 a 3/4, všechny) = 392 konfigurací na mřížku. Náklad 0,6 bodu.
- **Nulový model:** 200 stejných mřížek s náhodnou fází, tj. všechny čáry posunuté o náhodný zlomek cyklu.
- **Celkové (family-wise) p:** nejlepší konfigurace skutečné mřížky proti nejlepší konfiguraci každé náhodné mřížky.

## 4. Výsledky

### Celkové srovnání
| Mřížka | Doteků | Nejlepší excess R/obchod | Nejlepší u náhodných mřížek (průměr / 95 %) | Celkové p |
|---|---|---|---|---|
| W1 (konstanta 700) | 196 | +0,64 | +0,66 / +1,11 | 0,49 |
| D1 (konstanta 70) | 15 950 | +0,11 | +0,15 / +0,27 | 0,65 |

**Nejlepší výsledky skutečných čar jsou přesně takové, jaké dají náhodně posunuté čáry.**

### D1 (konstanta 70, 16 000 doteků)
- Ze 392 konfigurací jsou jen 3 na p < 0,05, méně, než dá náhoda.
- Fade se stejným TP i SL (1/8 – 2 cykly) má na všech typech čar excess −0,01 až +0,03 R, tedy nula.
- Čáry D1 se chovají jako náhodné čáry.

### W1 (konstanta 700)
- Jen 196 doteků za 18 let, konfigurace jsou silně korelované.
- Kladné výsledky mají malé n a nedrží napříč obdobími. Například breakout z poloviční čáry (TP 1 cyklus, SL 0,5): 2008–18 +0,23 R, 2018–26 +0,90 R, n = 23 / 19.

### Předem stanovená hypotéza
Z předchozího testu (`cycle_levels/`, jen 2018–26) vyšel odraz o 1/8 cyklu na červených a polovičních W1 čarách. Test na letech 2008–18, mimo vzorek:

| Čáry | 2008–18: n / win / R | p | 2018–26: n / win / R | p |
|---|---|---|---|---|
| červená + 1/2 (stanoveno předem) | 49 / 51 % / +0,01 | 0,61 | 46 / 61 % / +0,21 | 0,02 |
| jen červená | 26 / 62 % / +0,22 | 0,14 | 27 / 63 % / +0,26 | 0,045 |
| jen 1/2 | 23 / 39 % / −0,23 | 0,93 | 19 / 58 % / +0,15 | 0,15 |

**Hypotéza mimo vzorek neprošla.** Červené W1 čáry jsou kladné v obou obdobích, ale:
- je to dodatečně vybraná podmnožina;
- je to jen 26 obchodů;
- p mimo vzorek je 0,14.

Zatím to není důkaz. Dá se to jen sledovat dál.

## 5. Závěr
1. **Logika čar je vyřešená:** úrovně margin callu plně zapákovaného účtu (stop-out 30 %), geometrická řada a lineární čtvrtiny. Konstanta 70 / 700 = páka 25 / 2,5.
2. **Denní čáry (70)** nemají na S&P 500 2008–2026 žádný efekt v žádné variantě TP/SL. 16 000 doteků, výsledek jako u náhodných čar.
3. **Týdenní čáry (700):**
   - jsou vzácné (196 doteků za 18 let);
   - nejlepší varianta není lepší než nejlepší varianta náhodných čar;
   - předem stanovená hypotéza mimo vzorek neprošla.
4. **Na čem je to postavené:** předpoklad, že se na úrovních margin callů retailu „zastaví“ cena, je teoreticky zajímavý. Retail CFD účty ale index nehýbou a úrovně závisí na libovolném ukotvení. Data efekt nepotvrzují.
5. **Přikupování** z obchodního plánu edge nevytvoří, pokud ji nemá vstup. Viz Livermore: pyramidování bylo horší než plná pozice.

## 6. Dodatek: H1 čáry (konstanta 7)
- **Parametry:** cyklus 0,28028 % ceny (box 214 = 21,4 bodu při 7630). Červená kotva 7786,72 z uživatelova H1 grafu; sedí ±0,03 bodu.
- **Data:** jen 2018-07 – 2026-09 (data brokera, 1min). Rekonstrukce 2008–18 není dost přesná pro čáry po 2–5 bodech.
- **Rozsah:** 337 011 doteků, 392 variant TP/SL, horizont 10 dní, náklad 0,6 bodu.
- **Celkově:** nejlepší excess +0,016 R proti +0,015 R u nejlepší varianty náhodných mřížek, celkové p = 0,39. Na p < 0,05 je 12 variant ze 392, méně, než dá náhoda (≈ 20).
- **Fade se stejným TP i SL:** excess od −0,008 do +0,006 R na všech typech čar.
- **Náklady:** absolutní výsledky jsou záporné (−0,04 až −0,66 R), protože 0,6 bodu je u TP 1/8 cyklu (2,7 bodu) velká část. Před náklady by to byla nula.
- **Závěr:** H1 čáry se chovají přesně jako náhodné čáry. Po nákladech jsou ztrátové.
