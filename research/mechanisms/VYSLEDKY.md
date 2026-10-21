# Mechanismy z literatury otestované na ES2008 (21. 10. 2026)

Každá hypotéza má jedno pravidlo stanovené předem (bez ladění parametrů). Data ES 1min back-adjusted 2008–2026, náklady 0,5 bodu na obchod. Období 2008–15, 2016–20, 2021–26. Kód: `research/mechanisms/tests.py`, výsledky `out/*.csv`.

## Hlavní zjištění: tři „tokové“ edge zmizely kolem roku 2021

Tři nezávislé efekty, které souvisejí s nucenými toky, fungovaly do roku 2020 a v letech 2021–26 jsou nulové:

| Efekt | 2008–15 | 2016–20 | 2021–26 |
|---|---|---|---|
| Okno 02:00–03:00 ET (overnight drift), body za den | +0,23 (t 4,5) | +0,36 (t 2,6) | +0,07 (t 0,4) |
| Okno 02–03 po RTH výprodeji | +0,48 (t 3,6) | +0,59 (t 1,7) | −0,36 (t −0,7) |
| Intradenní momentum (hrubě), body | +0,25 (t 2,3) | −0,16 | −0,21 |
| Poslední 4 dny měsíce po slabém měsíci, % | +0,95 (t 2,3) | +1,27 (t 3,1) | −0,07 (t −0,2) |

To přesně odpovídá studii New York Fed (2026), že overnight drift od roku 2021 zmizel. Možné vysvětlení: změna mikrostruktury po roce 2021 (boom 0DTE opcí, víc systematických hráčů, front-running známých toků). To je hypotéza, z našich dat ji nelze prokázat. Praktický závěr: **edge založené na kalendáři a známých tocích stárnou**. Každý systém potřebuje průběžné sledování a kill kritérium.

## a) Overnight drift a noční reverze

- **Okno 02:00–03:00 ET**: celkem +0,21 bodu za den, t 3,1. Statisticky skutečný efekt (replikuje Boyarchenko a kol.), ale:
  - hrubých 0,21 bodu je méně než náklad 0,5 bodu, takže **na 1 ES kontraktu nebyl nikdy obchodovatelný**;
  - od 2021 zmizel.
- **Noční držení po RTH výprodeji** (dolní kvintil denního pohybu): +0,98 bodu, t 1,2. Nevýznamné.

## b) Intradenní momentum (Gao, Han, Li, Zhou)

- Znaménko pohybu od včerejšího close do 10:00 obchodované na posledních 30 minut:
  - hrubě ≈ 0 (t −0,04);
  - po nákladech −0,51 bodu na obchod (t −3,8).
- Ve dnech vysoké vol hrubě +0,52 bodu (t 1,1), nevýznamné.
- Na ES 2008–2026 se nereplikuje. Slabě fungovalo jen 2008–15.

## c) Konec a začátek měsíce (dash for cash, turn of month)

- Průměrný den +0,032 %.
- T-3 (třetí den před koncem měsíce) +0,125 % (t 2,0), T-1 +0,092 % (t 1,6), +1. den nového měsíce +0,081 %.
- Obchod turn-of-month (T až +3. den) +0,035 % denně, t 1,2. Nevýznamné.
- Slabý náznak efektu T-3 v souladu s Etula a kol. Sám o sobě ale na obchodování nestačí.

## d) Rebalancing (Harvey, Mazzoleni, Melone) – proxy přes ES

- **Po slabém měsíci** (dolní tercil výnosu do T-5) poslední 4 dny měsíce: +0,69 % (t 2,8, 64 % kladných, 74 měsíců).
  - Odpovídá nákupům akcií při rebalancingu po jejich podvýkonu.
  - **Platilo 2008–2020, v letech 2021–26 zmizelo** (−0,07 %).
- **Po silném měsíci** se očekávaný prodejní tlak neukázal (+0,10 %).
- Konce kvartálů: příliš málo pozorování (7–12 na období), nejednoznačné.

## e) Zpětné nákupy vol-control fondů

- Pravidlo: 10denní realizovaná vol ≥ 25 % a pak pokles o 20 % od vrcholu → long 20 dní.
- Jen 12 signálů od 2008: +0,52 ATR za 20 dní (t 0,8), nad průměrem roku v 10 z 12 případů.
- Ztráty v únoru 2009 (−9,6 %) a květnu 2022 (−5,5 %), oba uprostřed medvědího trhu.
- Směr odpovídá crisis allocatoru, ale **vzorek je moc malý** na samostatný systém.

## f) Falešná zotavení (P10)

- 14 rally o +5 % od dna při propadu ≥ 10 % od ročního maxima. 7 bylo falešných (nové dno do 120 dní): 4× 2008, březen 2020, květen a červen 2022.
- Falešná: výnos za 60 dní −1,6 %. Pravá: +11,8 %.
- Falešná přišla rychleji po dně (2,9 vs 4,0 dne) a při vyšší vol (41 vs 36 %). Při 14 případech to ale **není spolehlivý filtr**.
- Back-adjustment zmenšuje procentní propady v letech 2010–2012, takže tyto epizody nejsou zachycené. Na filtr falešného zotavení budou potřeba data mimo ES (šířka trhu, kreditní spready, VIX).

## Shrnutí pro portfolio

- Žádný z šesti nových testů nepřekonal laťku t ≥ 3 způsobem, který by šlo dnes obchodovat.
- Nejdůležitější poznatek je **rozpad tokových edge po 2021**. Platí i pro nás: pre-FOMC a vol-managed expozici je nutné sledovat průběžně.
- Nejsilnější zůstává: řízení expozice podle volatility, nákup panik (crisis allocator) a pre-FOMC (viz Regime Atlas).
