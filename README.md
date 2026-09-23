# session_edge: intradenní systémy nad nejvolatilnějšími okny seance

Jednoduché obchodní logiky, které využívají nejvolatilnější časová okna
seance, a statistický aparát, který rozhodne, jestli mají **skutečnou hranu**.

> **Na rovinu:** žádná logika není „neprůstřelná“ sama o sobě. Neprůstřelný
> může být jen **proces**, kterým hranu prokážeme nebo vyvrátíme: data bez
> look-ahead biasu, náklady, nulové hypotézy, korekce na počet pokusů,
> walk-forward a test na jiném trhu. Tento repozitář obsahuje obojí, tedy
> logiky i proces. Když systém validací neprojde, hranu nemá, ať vypadá
> equity křivka jakkoli.

---

## 1. Matematika hrany (co vlastně hledáme)

Výsledek obchodu měříme v **R** (násobcích rizika). Pro systém s pevným RRR:

```
E[R] = p · RRR − (1 − p) − náklady/riziko
```

Break-even win-rate: **p\* = 1 / (1 + RRR)**

| RRR | p\* (bez nákladů) | p\* s náklady 0,1 R |
|-----|------------------|---------------------|
| 1,0 | 50,0 %           | 55,0 %              |
| 1,5 | 40,0 %           | 44,0 %              |
| 2,0 | 33,3 %           | 36,7 %              |
| 3,0 | 25,0 %           | 27,5 %              |

Z toho plyne:

* **RRR samo o sobě hranu nevytváří.** Vyšší RRR jen snižuje potřebnou
  win-rate. Na náhodném trhu se win-rate s rostoucím RRR propadne
  přesně tak, aby E[R] zůstala ≈ 0 (minus náklady). Hrana je jedině
  v tom, že *vstup* posune pravděpodobnost nad p\*.
* **Náklady se měří v R.** Čím menší stop, tím větší podíl spreadu a skluzu
  v R. Pětiminutové ORB na úzkém rangu může mít náklady 0,2 R i víc.
* **Kolik obchodů potřebujete:** `N ≈ (1,96 · σ_R / E[R])²`. Při E[R] = 0,1 R
  a σ = 1,2 R to je **~550 obchodů**. Kratší backtest nic neprokazuje.
* **Velikost pozice:** Kelly pro R ≈ E[R] / E[R²]. Používejte ¼ Kelly,
  plný Kelly má brutální drawdowny.

## 2. Proč časová okna

Intradenní volatilita má tvar **U**: vysoká na otevření, útlum přes poledne,
znovu vysoká před zavřením. Na FX a zlatě jsou to navíc přechody seancí.
Soustředí se v nich order-flow: rebalancing, reakce na overnight zprávy,
makrodata, fixing, hedging opcí. Kde je koncentrovaný tok, tam vzniká
**předvídatelná struktura** (pokračování nebo vyčerpání). Hluché hodiny jsou
převážně šum.

Nejvolatilnější okna (ověřte na svých datech příkazem `profile`):

| Okno | Čas | Trhy |
|------|-----|------|
| US makrodata | 08:30 ET | vše, hlavně indexy, zlato, USD |
| **NYSE open** | 09:30–10:30 ET | ES, NQ, SPY, QQQ, akcie |
| **London open** | 07:00–10:00 Londýn | EUR, GBP, zlato, DAX |
| London/NY overlap | 13:00–16:00 Londýn | FX, zlato |
| WM/R fix | 16:00 Londýn | FX, zlato |
| **US close** | 15:30–16:00 ET | indexy (MOC, gamma hedging) |

Pozor na **letní čas**: USA a Evropa ho přepínají v jiné týdny. Proto
strategie pracují v **místním čase burzy** (`tz`), ne v UTC.

## 3. Brainstorming: varianty logik

Každá varianta má **hypotézu**, tedy *proč* by hrana měla existovat. Bez
hypotézy jde jen o data-mining.

### A) Opening Range Breakout (implementováno: `RangeBreakout`, `us_orb30`, `us_orb5`)
Range prvních 5/15/30 min po otevření, vstup na průraz, stop na opačné
straně (nebo ve středu) rangu, TP = RRR × riziko, výstup nejpozději na konci
seance.
*Hypotéza:* informace z otevření se do ceny promítá postupně, takže průraz
nese momentum. *Opora:* Zarattini & Aziz (2023) ukázali 5min ORB na QQQ
s kladnou hranou po nákladech. **Filtr komprese** (`max_range_atr`): obchodovat
jen, když je úvodní range úzký vůči ATR (komprese → expanze).

### B) Asijský range → London open (implementováno: `london_asia_breakout`)
Range 00:00–07:00 Londýn (klidná asijská seance), průraz 07:00–10:00.
*Hypotéza:* Londýn je největší FX centrum, první velký tok dne rozhodne
směr. Vhodné pro GBPUSD, EURUSD, XAUUSD.

### C) Falešný průraz / liquidity sweep (implementováno: `FailedBreakoutFade`)
Cena vyjede za range (vybere stopky), ale bar zavře zpět uvnitř → vstup
proti, stop za extrémem.
*Hypotéza:* průraz tažený stop-lossy, ne informací, se vrací. Je to přesný
**protipól A**, takže obě logiky zároveň mít hranu nemohou. Data rozhodnou,
na kterém trhu platí která.

### D) Intradenní momentum (implementováno: `IntradayMomentum`, `us_intraday_momentum`)
Výnos od včerejšího close do 10:00 ET určí směr, vstup v 15:30, výstup na
close.
*Opora:* Gao, Han, Li, Zhou (2018), *Market Intraday Momentum*, Journal of
Financial Economics. Jde o **nejlépe akademicky zdokumentovanou** variantu,
má skoro nulu volných parametrů (nízké riziko přeoptimalizace). Mechanismus:
gamma hedging dealerů a opožděné rebalancování. Doporučený start.

### E) Fade přepáleného gapu (implementováno: `GapFade`)
Gap 0,3–1,5 ATR, který v první půlhodině nepokračuje → vstup proti gapu.
*Hypotéza:* overnight přestřelení při nízké likviditě se po otevření
částečně koriguje. Obří gapy (zprávy) se nefadují.

### Další nápady k otestování (neimplementováno)
* **F) Overnight drift:** long na close, exit na open. Většina výnosu
  indexů historicky vzniká přes noc (Lou, Polk, Skouras 2019).
* **G) Režimový filtr:** A nebo D jen po dni NR7 / inside day, nebo jen
  když je VIX nad/pod mediánem. Filtr musí mít hypotézu, ne jen zlepšovat
  backtest.
* **H) Fix flow:** pohyb 15:30–16:00 Londýn před WM/R fixem na FX a zlatě
  (rebalancing podle konce měsíce).
* **I) Eventové okno:** průraz 5min rangu po 08:30 ET jen v dny NFP/CPI.
  Obchodů je málo, ale hrana bývá výraznější.
* **J) Kombinace A + D:** ORB ráno, momentum odpoledne. Diverzifikace
  v čase je jediný „free lunch“.

## 4. Nastavitelné parametry

| Parametr | CLI | Význam |
|----------|-----|--------|
| SL | `--stop-mode strategy\|atr\|points\|range --stop X` | stop dle strategie / X×ATR / X bodů / X×range |
| TP | `--target-mode rrr\|atr\|points\|none --target X` | TP; výchozí přes RRR |
| RRR | `--rrr 2.0` | TP = riziko × RRR |
| Max. obchodů | `--max-trades 2` | za den; současně max. 1 otevřená pozice |
| Uzavření | `--exit-time 15:55` | nucený výstup (čas zóny strategie); bez něj konec dne |
| Break-even | `--breakeven 1.0` | SL na vstup po +1 R |
| Náklady | `--cost 0.5` | spread + poplatek + skluz round-trip v bodech ceny |
| Parametry strategie | `--set range_end=09:45 --set max_range_atr=0.3` | cokoli ze třídy strategie |

## 5. Validační protokol (co musí systém splnit)

`validate` vypíše 7 kontrol. **Kandidát na hranu** je jen systém, který
projde všemi:

1. **E[R] > 0 po nákladech.**
2. **t-stat > 2** (p < ~0,025 jednostranně).
3. **Bootstrap 95% CI** expectancy celý nad nulou.
4. **Test náhodného směru:** stejné časy vstupu, stejný SL/TP, směr určuje
   hod mincí (200×). Systém musí porazit 95 % náhodných běhů. Tím se odfiltruje
   „hrana“, která je ve skutečnosti jen v struktuře SL/TP nebo v trendu dat.
5. **Deflated Sharpe > 0,95.** Korekce na počet vyzkoušených variant
   (`--trials`). Vyzkoušeli jste 50 kombinací? Zadejte `--trials 50`.
   Jinak jen vybíráte nejšťastnější náhodu.
6. **Kladná většina let.** Hrana nesmí stát na jednom roce.
7. **≥ 100 obchodů** (ideálně stovky).

Pak:

8. **Walk-forward** (`walkforward`): parametry se vybírají na tréninkovém
   okně a měří na následujícím neviděném. Rozhoduje jen spojený OOS výsledek.
9. **Jiný trh / jiné období:** ORB z ES musí fungovat aspoň rozumně i na NQ.
10. **Monte Carlo:** drawdown v 95. percentilu musíte psychicky i finančně
    unést.

**Pozor na průrazové vstupy a skluz:** stop order se v backtestu plní přesně
na úrovni průrazu. Na hrubých datech nebo v rychlém trhu je reálné plnění
horší, a to systematicky *proti* obchodu. U malých rangů (ORB 5m) tak
i 1–2 ticky skluzu mění výsledek. `--cost` proto vždy nastavte aspoň na
spread + 1 tick skluzu na vstupu i na stopu (ES: 0,5 bodu).

Engine je navíc konzervativní: ATR jen z minulých dní, na vstupním baru
průrazu se počítá jen SL, když bar zasáhne SL i TP, počítá se SL, a gapy
přes SL se plní na open.

## 6. Použití

```bash
pip install -r requirements.txt

# kde je trh nejživější (profil volatility podle času a dne)
python -m session_edge profile --csv es_5m.csv --data-tz UTC --tz America/New_York

# plná validace
python -m session_edge validate --csv es_5m.csv --data-tz UTC \
    --strategy us_orb30 --rrr 2 --max-trades 1 --exit-time 15:55 --cost 0.5 --trials 10

# intradenní momentum
python -m session_edge validate --csv es_5m.csv --strategy us_intraday_momentum \
    --target-mode none --stop-mode atr --stop 0.5 --exit-time 15:59

# London breakout na zlatě
python -m session_edge validate --csv xauusd_5m.csv --data-tz UTC \
    --strategy london_asia_breakout --rrr 1.5 --exit-time 16:00 --cost 0.3

# walk-forward
python -m session_edge walkforward --csv es_5m.csv --strategy us_orb30 --exit-time 15:55

# demo bez dat: náhodná procházka (hrana nesmí vyjít) a data s vloženou hranou
python -m session_edge validate --synthetic --strategy us_orb30 --exit-time 15:55
python -m session_edge validate --synthetic --inject-edge 0.2 --strategy us_orb30 --exit-time 15:55

python -m session_edge list   # seznam předvoleb
pytest -q                     # testy
```

**Data:** CSV s OHLC (1–15 min), ideálně 3+ roky. Loader zvládne export
z TradingView, MT4/MT5 (`<DATE> <TIME> ...`), Dukascopy i unix timestampy.
`--data-tz` je zóna časů v souboru (MT5 servery bývají UTC+2/+3).

## 7. Struktura

```
session_edge/
  config.py      RiskConfig: SL/TP/RRR, max. obchodů, exit_time, BE, náklady
  strategies.py  logiky A–E + předvolby
  engine.py      bar-by-bar simulace bez look-ahead biasu
  stats.py       expectancy, t-test, bootstrap, DSR/PSR, Kelly, Monte Carlo
  validation.py  validační protokol + walk-forward
  profile.py     profil volatility podle času a dne v týdnu
  data.py        načítání CSV, syntetická data
tests/           unit testy enginu a statistiky
```
