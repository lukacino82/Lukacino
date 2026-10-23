# Obrácené RRR s TP/SL v ATR – rozšířená knihovna signálů (23. 10. 2026)

## Zadání
- **Signály:** najít co nejvíc signálů s obráceným RRR (zisk menší než ztráta).
- **TP a SL:** v násobcích ATR(14) předchozího dne.
  - TP 0,08–0,5 ATR;
  - SL 0,08–3 ATR;
  - RRR až 1:37.
- **Vstup:** v pevnou hodinu po situaci na trhu.
- **Obchodování:** automatické.
- **Měřítko:** buy & hold ES.

Kód: `atr_signals.py`, `atr_select.py`, `atr_family.py`, `bear_momentum.py`; výsledky v `out/atr_*.csv` a `out/bear_momentum_*.csv`.

## Rozsah
- **116 pravidel stanovených předem**, všechny prahy v ATR:
  - pohyb za posledních 30/60/120 min;
  - pohyb od otevření globex session;
  - gap proti včerejšímu close;
  - pod včerejším low / nad high;
  - předchozí den ±0,5/1 ATR;
  - RSI(2), IBS, 3 dny dolů/nahoru, 5denní low/high;
  - režim volatility, den v týdnu.
  Intradenní pravidla i s filtrem režimu (nad/pod MA200).
- **Kombinace:** × 44 časů vstupu (18:00–15:30 ET, po 30 min) × 8 TP × 14 SL × long/short × do close / 5 dní.
- **Celkem 2,2 mil. kombinací**, výsledky v ATR na obchod po nákladech 0,5 b.
- **Výběr:** jen na letech 2008–17 (s penalizací jedné plné ztráty SL). Roky 2018–21 a 2022–26 slouží jako test.

## 1. Výběr konkrétních nastavení: in-sample skvělé, mimo vzorek nula
Kladná edge proti náhodnému vstupu ve stejném čase, v letech 2022–26:

| Skupina | Top 20 | Top 100 | Náhodný výběr |
|---|---|---|---|
| Long, obrácené RRR (SL ≥ 2×TP) | 25 % | 46 % | 55 % |
| Long, RRR ≤ 1:1 | 45 % | 50 % | 53 % |
| Short, vše | 95 % | 87 % | 48 % |

Short je kladný v OOS, ale ve VAL 2018–21 záporný.

Automatické portfolio 25 nejlepších long signálů s obráceným RRR (vybraných na 2008–17), riziko 0,5 % účtu na obchod, TP/SL v ATR:

| Období | Systém CAGR | Sharpe | Max DD | B&H CAGR | B&H Sharpe |
|---|---|---|---|---|---|
| 2009–2026 | 11,4 % | 1,44 | −18 % | 9,5 % | 0,74 |
| 2018–2026 (mimo výběr) | 1,3 % | 0,19 | −18 % | 9,5 % | 0,65 |
| 2022–2026 | 4,5 % | 0,55 | −18 % | 7,0 % | 0,52 |

Rozpad po letech:
- 2009–2017: každý rok +15 až +30 %, win 80–85 %, 15–28 zásahů SL ročně.
- 2018–2026: win 69–79 % a 35–79 zásahů SL ročně. Výsledky −11,5 / +12,5 / −7,0 / −1,6 / +4,2 / +5,4 / −7,8 / +5,7 / +15,3 %.

Přesně to je past obrácených RRR: v klidném vzorku SL skoro nepřijde a výběr preferuje pravidla, kde se nikdy netrefil. Po roce 2018 (Volmageddon, covid, 2022) se zásahy SL ztrojnásobily.

## 2. Výběr celých rodin pravidel (méně přeučení): stejný výsledek
- **Postup:** 52 rodin vybraných na 2008–17. Ve VAL kladných 81 %, v OOS 69 % (všechny rodiny 55 % / 55 %).
- **Rodiny tedy nesou trochu informace.** Kladné ve VAL i OOS je 56 % vybraných proti 33 % u všech.
- **Portfolio** (pevné TP/SL a 3 časy na rodinu z let 2008–17):
  - 2009–17: +29 až +96 % ročně;
  - 2018–26: CAGR −0,4 %;
  - 2022–26: 9,0 % (Sharpe 0,60, B&H 0,52).
- **Korelace s ES** je 0,03, takže B&H + systém v letech 2022–26 dává Sharpe 0,78. V letech 2018–21 ale −30 % a −22 %.

## 3. Jediný konzistentní vzor: intradenní momentum v medvědím režimu
- **Long po růstu:** když je ES pod MA200 a od otevření session vyroste o ≥ 0,6–1 ATR, long do close vyšel kladně v 95–100 % kombinací v letech 2008–17, 86–100 % v 2018–21 a 68–100 % v 2022–26.
- **Short po propadu:** zrcadlově 90–98 % / 53–86 % / 52–92 %.
- **V býčím režimu** efekt není.

Jednoduchý automatický systém s předem pevnými pravidly: ES pod MA200, první pohyb ±1 ATR od otevření session mezi 10:00 a 15:00 ET, obchod ve směru pohybu.

| Exit | Obchodů | R/obchod | t | 2009–17 | 2018–21 | 2022–26 |
|---|---|---|---|---|---|---|
| do close | 187 | +0,063 | 1,45 | +0,074 | +0,052 | +0,059 |
| TP 0,3 / SL 1,5 ATR (obrácené) | 187 | +0,042 | 1,38 | +0,053 | +0,038 | +0,033 |
| TP 0,4 / SL 0,8 ATR | 187 | +0,043 | 1,46 | +0,069 | −0,036 | +0,056 |

- Kladné ve všech obdobích, ale jen ~10 obchodů ročně a t < 2. Zisk tvoří hlavně roky 2011 a 2020; v roce 2022 ztráta.
- Při prahu 0,6 ATR efekt slábne a v letech 2022–26 je nulový.
- Kandidát na paper trading a krizový doplněk k B&H, ne hotový systém.

## Závěr pro tvoji tezi
1. **Automatizace je jednoduchá.** Systém, který každý den spočítá ATR(14), nastaví TP a SL jako násobek ATR a v danou hodinu po splnění podmínky otevře obchod, je technicky triviální (Sierra Chart ACSIL nebo attached orders s offsetem z ATR).
2. **Vysoký win rate není potřeba a obrácené RRR edge nevytváří.** Win rate se drží na SL/(TP+SL), tedy na hodnotě čisté náhody. Očekávaná hodnota je drift minus náklad plus to, co přidá vstupní podmínka.
3. **Historicky „nejlepší“ obrácené RRR jsou nejhorší volba.** Vybírají pravidla, kde se ve vzorku nestala černá labuť. Na 2,2 mil. kombinací a se dvěma metodami výběru: in-sample Sharpe 1,4, mimo vzorek 0,1–0,6.
4. **Co dlouhodobě porazilo B&H:**
   - řízení expozice (vol target, crisis allocator, viz Regime Atlas);
   - jako nekorelovaný doplněk k B&H případně medvědí momentum.
   Samostatné intradenní obrácené RRR B&H mimo vzorek neporazilo.
