# Livermore na ES 2009–2026 (23. 10. 2026)

Kód: `livermore/livermore.py`, výsledky `livermore/out/*.csv`.

## Principy převedené na pravidla (stanovená předem)
Zdroje: *How to Trade in Stocks* (1940), *Reminiscences of a Stock Operator* (1923, Project Gutenberg #60979).

| Princip | Pravidlo v testu |
|---|---|
| Pivotal point | Vstup long jen při průrazu: nové 20 / 55 / 252denní maximum close |
| Pyramidování | Sonda 20 %, +20 % při +1 ATR, +20 % při +2 ATR, +40 % při +3 ATR. Přidává se jen do zisku, nikdy se neprůměruje dolů |
| Cut losses | Počáteční stop 2 ATR, varianta 10 % (Livermorova max. ztráta) |
| „Když se nechová správně, ven“ | Časový stop: po 10 dnech není v zisku → výstup |
| Sit tight | Výstup jen při „přirozené reakci“: close o 3 nebo 6 ATR pod maximem, varianta pod 20denním low |
| Market Key | Zigzag pivoty s prahem 2/3/4 ATR. Long nad posledním pivotem high + ½ prahu, flat (nebo short) pod pivotem low − ½ prahu |

**Exekuce:** na open dalšího dne, náklad 0,5 b. na kontrakt.

**Srovnání:**
- tatáž pravidla bez pyramidy;
- náhodné vstupy se stejnou pyramidou a výstupy (200×);
- buy & hold.

## Výsledky (2009–2026, 42 variant)
| Systém | Expozice | CAGR | Sharpe | Max DD | Alfa/rok | Alfa t |
|---|---|---|---|---|---|---|
| Buy & hold ES | 100 % | 9,4 % | 0,74 | −28 % | – | – |
| Nejlepší: průraz 20D, plná pozice, výstup reakce 6 ATR | 83 % | 7,6 % | 0,80 | −14 % | +2,5 % | 1,58 |
| Totéž s pyramidou | 74 % | 5,5 % | 0,66 | −18 % | +1,3 % | 0,88 |
| Průraz 55D, pyramida, reakce 3 ATR | 29 % | 0,9 % | 0,23 | −12 % | −0,3 % | −0,32 |
| Průraz 252D (nová roční maxima), pyramida, 20denní low | 22 % | −0,3 % | −0,05 | −11 % | −1,2 % | −1,37 |
| Market Key 3 ATR, long/flat | 78 % | 5,9 % | 0,65 | −20 % | +1,2 % | 0,75 |
| Market Key 3 ATR, long/short | 98 % | 1,6 % | 0,18 | −29 % | +2,4 % | 0,75 |

## Hlavní zjištění
1. **Žádná varianta nemá prokazatelnou alfu.** Nejlepší t-statistika je 1,58, laťka je 2 (u 42 variant spíš 3). Nejlepší Sharpe 0,80 je jen o kousek nad B&H (0,74), CAGR je nižší (7,6 vs 9,4 %).
2. **Pyramidování na ES škodí.** Ve všech srovnatelných dvojicích má verze s pyramidou nižší CAGR, Sharpe i alfu než plná pozice hned při vstupu. Důvod: ES na horizontu dnů až týdnů spíš vrací (Swing Alpha). Přikupování po růstu o 1–3 ATR kupuje draho a následná reakce vyhodí celou pozici.
3. **Náhodné vstupy se stejnou pyramidou a výstupy dopadly lépe** než Livermorův průraz 55D. Průměrný Sharpe náhodných vstupů byl 0,42, průraz měl 0,23 (p = 0,92). Samotný „pivotal point“ tedy na ES informaci nenese.
4. **Profil výsledků přesně odpovídá Livermorovi:**
   - win rate 40–58 %;
   - průměrný zisk 2–11× větší než průměrná ztráta;
   - 35–56 % celého zisku přináší 10 % nejlepších obchodů.
   „Velké peníze se dělají sezením“ platí, jen to na ES nepřekoná prosté držení.
5. **Nová roční maxima (252D)** jsou nejhorší vstup (alfa t −0,8 až −1,4). To potvrzuje Edge Factory: po novém 52týdenním maximu ES roste pomaleji.
6. **Market Key long/short** ztrácí na shortech (drift ES). Long/flat jen kopíruje B&H s menší expozicí.

## Proč Livermorovi fungoval a nám ne
- **Jiný trh.** Obchodoval desítky akcií a komodit v letech 1900–1930, v méně efektivních trzích s pomalým šířením informací a silnými trendy.
- **Diverzifikace přes trhy.** Trendový princip dnes prokazatelně funguje jen jako trend-following přes desítky trhů (time-series momentum, CTA). Na jediném indexu ES je slabý.
- **Jeho vlastní výsledky měly obrovský rozptyl.** Několikrát zbankrotoval (mj. 1934) a jeho slavné výhry (1907, 1929) jsou malý vzorek.
- **Ověřitelná systematická pravidla nikdy nezveřejnil.** Jeho principy jsou diskreční; „pivotal point“ a „Market Key“ jsou interpretace.

## Co z Livermora použít
- **Řízení rizika a psychologie platí:** malá sonda, nepřidávat do ztráty, rychle řezat ztráty, nechat zisky běžet.
- **Trendovou logiku nepoužívat na samotném ES.** Má smysl až v portfoliu více trhů (NQ, ZN, CL, GC, měny), tedy trend-following CTA, k čemuž potřebujeme další data.

---

# One-Day Reversal (Livermore) na ES 2009–2026

Kód: `livermore/reversal.py`, výsledky `out/reversal_events.csv` a `out/reversal_system_years.csv`.

## Pravidla (podle zadání)
| Signál | Podmínky | Obchod |
|---|---|---|
| Býčí reverz | close > předchozí close, low < předchozí low, objem > předchozí objem | long |
| Medvědí reverz (jak je v zadání) | close < předchozí close, low > předchozí low, objem > předchozí objem | short |
| Medvědí reverz (klasický key reversal) | close < předchozí close, high > předchozí high, objem > předchozí objem | short |

**Varianty:** bez podmínky objemu; „po pohybu“ (býčí: low je 20denní minimum, medvědí: high je 20denní maximum).

**Měření:** vstup na open dalšího dne, výstup na close po 1, 2, 3, 5 a 10 dnech, v ATR, po nákladech.

**Excess:** výsledek minus průměrný den téhož roku na stejné straně, tím se odečte drift ES. Bere se jen nepřekrývající se signály.

## Výsledky
- Excess je nevýznamný ve všech 35 kombinacích (7 signálů × 5 horizontů). Nejvyšší |t| je 1,5, laťka je 2. Znaménko se mezi obdobími 2009–17, 2018–21 a 2022–26 mění.
- **Býčí reverz na 10 dní** vypadá dobře (+0,41 ATR, t 2,6, win 63 %). Je to ale jen drift ES: excess proti průměrnému dni je +0,05 ATR (t 0,3).
- **Medvědí reverzy** prodělávají (t −2 až −3), protože shortují proti driftu. Proti průměrnému dni jsou kolem nuly.
- **Varianta „po pohybu“** (reverz z 20denního low/high): málo signálů (37–149) a bez konzistence.
- **Podmínka vyššího objemu** nic nepřidává. Varianty bez objemu dopadly stejně nebo lépe.
- **Jednoduchý systém** (býčí reverz, long na 5 dní, stop 1 ATR): CAGR 0,5 %, t 0,53, v trhu 18 % dní. B&H 9,4 %.

## Závěr
One-day reversal na ES samostatně edge nemá. Podobně jako jiné svíčkové vzory (Edge Factory: 3 157 hypotéz) se chová jako šum. Livermore ho používal jako upozornění v kontextu (vyvrcholení dlouhého trendu u konkrétní akcie), ne jako mechanický vstup.
