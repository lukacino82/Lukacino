# Obrácené RRR a hodiny na ES (23. 10. 2026)

Pravidla stanovená předem, pak průchod přes ES2008 (1min, 05/2008–09/2026).

**Vstupy**
- Každých 30 minut od 18:00 do 15:30 ET, long i short, celkem 204 601 vstupů.
- TP 4–25 b. × SL 4–150 b., tj. RRR od 1:1 do 1:37.
- Podmínky: pohyb předchozí hodiny ±5/10/15/20 b., gap pod včerejším close, ES nad MA200.

**Výstupy a hodnocení**
- Horizont do close RTH a 5 dní, body i ATR škálování, náklad 0,5 b.
- Výběr jen na 2008–17; 2018–21 a 2022–26 jsou test.
- Kód: `irr_engine.py`, `build.py`, `irr_analysis.py`, `summarize.py`, `playbook.py`, `deep.py`.
- Report: `out/ES_Inverse_RRR.html` / `.pdf`.

## 1. Obrácené RRR samo edge nedává
- Náhodný long v 09:30 drží win rate přesně na náhodné procházce SL/(TP+SL), např. 10/100 → 91 %. Expectancy je ve všech nastaveních ≈ drift − náklad:

| Nastavení | b./obchod | Ziskových let |
|---|---|---|
| 1:1 (15/15) | −0,27 | 8 z 19 |
| 1:3 (10/30) | −0,37 | 4 z 19 |
| 1:10 (10/100) | −0,44 | 7 z 19 |

- 1 310 kombinací vypadalo „robustně“ (kladné ve všech obdobích), často s win 100 % a t = ∞. To je artefakt: SL se ve vzorku nikdy netrefil.
- Oprava: do každého vzorku přidat jednu plnou ztrátu SL („černá labuť“), pak výběr jen na 2008–17.
- Výsledek top 20 long obrácených RRR (SL ≥ 3× TP):

| Období | b./obchod |
|---|---|
| 2008–17 | +2,8 |
| 2018–21 | +0,6 |
| 2022–26 | **−1,5** |

- Kladnou OOS edge mělo jen 10 % z top 20, méně než při náhodném výběru (44 %). Klidný býčí vzorek bez černé labutě vybírá přesně ta pravidla, která rok 2022 zničil.
- Long 1:1 top 20: OOS −0,26 b. Long TP 12–25: OOS −0,55 b.

## 2. Hodiny
- P(long dosáhne +15 b. do close) a P(−15 b. do close) jsou v každé hodině skoro stejné. Hodina dává čas do close, ne směr.
- Rozhoduje volatilita roku. Vstup 09:30, +15 b. do close: 2017 (ATR 14) 7 %, 2022 (ATR 80) 71 %, 2025 (ATR 68) 65 %. Pevné body = každý rok jiná strategie, TP/SL je nutné dávat v ATR.
- Typická korekce před ziskem +15 (vstup 09:30):

| Korekce proti obchodu | Podíl vítězů |
|---|---|
| ≥ 4 b. | 58 % |
| ≥ 10 b. | 30 % |
| ≥ 20 b. | 14 % (90% kvantil) |

  Medián korekce je 4 b., 75% kvantil 12 b. Stop 4 b. zabije 58 % budoucích vítězů.
- Dny v týdnu a měsíce: u náhodných vstupů rozdíly v řádu desetin bodu, šum.

## 3. Deset pevně zadaných kandidátů (long, 1 obchod denně, do close)
- Náhodné vstupy 09:30 (1:1, 1:3, 1:10) ztrácí. B&H porazily jen ve 2–3 letech z 19.
- Neprošly:
  - DN_10 09:30 (15/15 i 10/50);
  - GAPDN_20_BULL 09:30.
- Malý vzorek, vzor „sbírání drobných“:
  - UP_10 22:00 (10/150): 89 obchodů, 1 SL;
  - DN_5_BULL 01:00 (20/150): 112 obchodů, 1 SL.
  - Oba +6–9 b./obchod, ale v letech 2008–17 jen 3–4 signály a jeden zásah SL = −150 b.
- Žádný kandidát nepřekonal B&H v bodech za rok. Nad B&H byly jen v medvědích letech (2008, 2018, 2022).

## 4. Co přežilo test okolí parametrů
**A. Short v 10:00 po propadu první hodiny o ≥ 0,3 ATR, TP = SL = 0,4 ATR, jinak exit na close.**
- Vybráno jen na 2008–17.
- 436 obchodů, win 57 %, max DD −158 b.

| Období | b./obchod |
|---|---|
| 2008–17 | +1,5 |
| 2018–21 | +1,4 |
| 2022–26 | +5,3 |

- V bodech je kladných 83 % okolních nastavení v OOS a 79 % v letech 2008–17. V ATR variantě jen 51 % (09:30–11:00), slabší je 10:30.
- Zrcadlový long po růstu první hodiny je v OOS taky kladný (88 % okolí). Jde tedy o intradenní momentum po otevření, ne o short efekt. Silné v medvědích letech (2008 +110 b., 2022 +223 b.).
- Možný mechanismus (hypotéza): zajišťování dealerů s negativní gammou (0DTE). Literatura: Baltussen a kol. 2021.

**B. Long v 09:00 po poklesu 08:00–09:00 o ≥ 10 b., TP 6 / SL 30, jinak exit na close.**
- 250 obchodů, win 90 %, 20 SL, max DD −122 b., ziskových 17 ze 17 let.

| Období | b./obchod | t |
|---|---|---|
| 2008–17 | +5,0 | n = 29 |
| 2018–21 | +3,4 | 2,7 |
| 2022–26 | +1,8 | 2,2 |

- Okolí v čase 09:00: OOS kladné 89 % (body) a 81 % (ATR) kombinací. Fungují prahy 10/15/20 b., TP 6–12, SL 20–50. Práh 5 b. a TP = SL 15 nefungují.
- Sousední časy 08:00, 08:30 a 09:30 nefungují. Efekt je vázaný na pokles kolem makro dat v 8:30, který se před otevřením RTH částečně vrátí.
- Pozor: nalezeno na celém vzorku, před 2020 jen 1–10 signálů ročně. Kandidát na paper trading, ne hotový systém.

## Pravidla do praxe
1. Win rate vždy porovnat s SL/(TP+SL).
2. Obrácené RRR = prodej opce: velikost podle ztráty SL (= 10–25 výher), ne podle win rate.
3. TP a SL v ATR.
4. SL ne pod typickou korekci (0,2 ATR pro cíl 0,3 ATR).
5. Hodina sama edge nemá, rozhoduje situace (data v 8:30, směr první hodiny).
6. A a B paper trading 3–6 měsíců se zamčenými pravidly. Kill: 3 měsíce pod nulou.
