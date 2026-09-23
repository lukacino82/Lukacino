# ES futures 2018–2026: kde je hrana a kde není

Data: ES kontinuální kontrakt, 1min bary ze Sierra Chart, 07/2018 až 09/2026
(2,9 mil. barů, 2 046 RTH dní). Časy jsou v ET. Náklady 0,5 bodu na round-trip
(2 ticky: spread + poplatek + skluz). Detailní tabulky jsou v `REPORT.md`,
skripty v `analysis/run_all.py` a `analysis/research/`.

## Shrnutí

| Logika | Obchodů | E[R] | t | Walk-forward OOS | Verdikt |
|---|---|---|---|---|---|
| **Gap fade** (gap 0,2–1,5 ATR, potvrzení do 10:00, RRR 2) | 613 | **+0,132** | **2,50** | +0,104 R, t 1,95 | **jediný kandidát**: 6/7 kontrol, náhodný směr p = 0,01 |
| ORB 30m (úzký range, RRR 3 / držení do close) | 1 282 | +0,054 | 1,40 | +0,100 R, t 2,22 | slabé, nekonzistentní (2019 −0,14 R) |
| ORB 15m | 1 216 | +0,052 | 1,13 | +0,078 R, t 1,47 | bez hrany |
| ORB 5m | 2 102 | −0,065 | −1,80 | −0,051 R | záporné (náklady na malém rangu) |
| ORB fade (liquidity sweep) | 1 108 | −0,009 | −0,28 | −0,100 R | bez hrany |
| Intradenní momentum (Gao et al.) | 2 018 | −0,030 | −3,43 | −0,028 R | **na ES neplatí** |
| Europe open breakout | 1 604 | −0,019 | −1,23 | −0,046 R | bez hrany |

## 1. Co jsme se o ES dozvěděli (struktura trhu)

* **Nejvolatilnější okna:** 09:30–10:30 ET (2,3× průměr dne), 15:30–16:00
  (1,8×) a 08:30 (makrodata). Evropské otevření (03:00 ET) je jen 1,1×.
* **ES je intradenně mírně mean-reverting.** Poměr rozptylů 5min výnosů je
  pro 60 min 0,83 a je pod 1 v každém z 9 let. Autokorelace 5min výnosů je
  −0,04. To vysvětluje, proč průrazy (ORB) nefungují: průraz je častěji
  šum, který se vrátí.
* **Reverze je ale na retailové náklady příliš malá.** Očekávaný návrat
  je řádově 0,1 bodu na 5min bar a náklady jsou 0,5 bodu. Přímý fade
  přetažených pohybů (30/60/120 min i od VWAP) po nákladech ztrácí.
* **Intradenní momentum ze studie Gao et al. (2018) se na ES 2018–2026
  neprojevuje.** Znaménko ranního pohybu poslední půlhodinu nepredikuje.
  Pořadová korelace je ≈ 0, Pearsonova je mírně záporná díky pár
  extrémním dnům v roce 2020.
* **Denní a kalendářní efekty** (pondělí, den po velkém poklesu,
  turn-of-month, noční drift +3 bp/noc) mají správné znaménko, ale
  t < 2. Samostatně je nelze obchodovat.

## 2. Kde hranu vidím: Gap fade

**Logika:** RTH otevře s gapem 0,2–1,5 denního ATR proti včerejšímu RTH
close. Když cena do 10:00 nepokračuje ve směru gapu (close v 10:00 je
zpět za open), vstup proti gapu. Stop je za extrémem prvních 30 min, TP
je 2R a nucený výstup v 15:55.

**Hypotéza:** noční pohyb vzniká v tenké likviditě a přestřelí. Když po
otevření RTH chybí pokračování, velká likvidita ho částečně vrátí.
Sedí to se zjištěnou mean-reverzí ES.

**Co pro hranu mluví:**
* Test náhodného směru: p = 0,01 (p = 0,003 u varianty s TP na zavření
  gapu). Informace je tedy v *nápadu směru*, ne ve struktuře SL/TP.
* Bootstrap 95% CI [+0,03; +0,24] R.
* Walk-forward (parametry vybrané jen z minulosti): OOS +0,104 R, t 1,95.
* **Plató parametrů:** kladná E prakticky v celé mřížce 72 kombinací
  (min. gap 0,1–0,4 ATR × potvrzení 09:45/10:00/10:15 × RRR). Nejde
  o osamocený vrchol.
* Kladná v 8 z 9 let. Short strana (fade gapu nahoru) je silnější,
  +0,16 R (t 2,2), long +0,09 R.
* Max. drawdown 18 R. Monte Carlo při riziku 1 %/obchod: medián max DD
  ~20 %, pravděpodobnost ztráty 50 % kapitálu 0 %.

**Co proti ní mluví (proto „neprokázané“):**
* Po korekci na počet vyzkoušených variant je Deflated Sharpe 0,76
  (16 variant), resp. 0,22 (~100 variant). Laťka pro jistotu je 0,95.
* **Rok 2026 je zatím záporný** (−0,22 R, 54 obchodů). Může to být šum,
  ale i začátek degradace.
* **Silná citlivost na náklady:** 0,25 bodu → t 3,0, 0,5 → t 2,5,
  1,0 → t 1,4, 1,5 → t 0,3. Hrana je jen ~1,5 bodu na obchod.
* Jen ~75 obchodů za rok, takže statistika se hromadí pomalu.

## 3. Kde by se dala hrana posunout dál

1. **Exekuce (největší páka).** Při 0,25 bodu nákladů vyskočí t z 2,5
   na 3,0. Vstup gap fade je na close baru v 10:00 a dá se nahradit
   limitkou o tick lepší. Stop-loss plnit reálně, ne přes market s
   velkým skluzem. Na ES znamená každý ušetřený tick +0,02 R na obchod.
2. **Asymetrie long/short.** Fade gapu nahoru je silnější. Obchodovat
   jen short, nebo short s plnou a long s poloviční velikostí. Pozor:
   to je další „pokus“, který se musí ověřit na nových datech
   (paper trading), ne v tomto vzorku.
3. **Out-of-sample na jiném trhu.** Stejná logika na NQ, YM a RTY bez
   změny parametrů. Pokud tam platí, je to nejsilnější možný důkaz.
   Na to potřebuji data.
4. **Forward test 2026+.** Parametry teď zmrazit a 6–12 měsíců jen
   sledovat (paper nebo 1 MES). Rok 2026 je zatím záporný, tohle
   rozhodne.
5. **Co nedělat:** kombinovat s ORB 30m (korelace 0,49 ve společné dny,
   portfolio má horší t), přidávat filtry dne v týdnu nebo ATR (žádný
   nemá |t| > 2, byl by to jen data-mining), ani ladit RRR (plató je
   ploché).

## 4. Kde hranu nevidím

* **ORB 5m** je po nákladech jasně záporný. Při rangu kolem 5 bodů
  sežerou 2 ticky přes 0,1 R. Studie Zarattini & Aziz testovala QQQ a
  akcie „in play“, ne ES.
* **ORB 15/30m** se pohybuje kolem nuly. Roste s RRR (nechat zisky
  běžet), ale t < 1,5. Rok 2019 −0,14 R. Filtry (směr gapu, trend,
  ATR, den) nepomohly.
* **Intradenní momentum a fade liquidity sweep** jsou záporné nebo
  nulové.
* **Evropské otevření na ES** je záporné. Na ES je to druhotná seance,
  logika B je určená pro FX a zlato.

## 5. Důležité opravy během analýzy

* **Engine** měl dvě chyby ve prospěch průrazů: TP se nekontroloval
  na vstupním baru a vynechávaly se „outside bary“, které prorazily
  obě strany. Obě jsou opravené a ověřené proti nezávislému simulátoru
  na tickové cestě. Bez oprav by ORB vypadal jako hrana.
* **Look-ahead v analýze:** filtr „směr včerejšího dne“ nejdřív omylem
  používal dnešní close (t = +12). Po opravě je t = 0,6. Přesně takové
  chyby dělají z backtestů „neprůstřelné“ systémy.

## 6. Omezení dat

* Kontinuální kontrakt není back-adjustovaný. Asi 4× ročně vznikne na
  pondělním RTH open „gap“ z rolu (carry, 60–100 bodů). U gap fade to
  působí *proti* strategii (roll gap se nezavře), takže výsledek spíš
  podhodnocuje.
* Plnění stop orderů přesně na úrovni. Na 5min barech je u průrazů
  mírně optimistické a pokrývají ho náklady 0,5 bodu.
