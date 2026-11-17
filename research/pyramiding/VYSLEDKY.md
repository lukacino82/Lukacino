# Pyramiding (přikupování k vítězi s klesajícím rizikem): vytvoří edge, nebo ne?

**Zadání:** text videa (Pyramiding vs Martingale): první vstup 1R, přidání jen po příznivém pohybu a jen s menším rizikem (0,5R, 0,25R, 0,1R), celá pozice se stopem posouvá na předchozí úroveň, takže velikost roste a riziko klesá. Může to samo dát edge, nebo jak z toho vzít použitelné principy?

## Závěr ve zkratce
1. **Pyramiding sám edge nevytváří.** Je to pravidlo velikosti pozice a řízení stopu, ne zdroj očekávané hodnoty. U ceny, která se blíží náhodné procházce (martingale), je střední hodnota každého přidání nula a žádné posouvání stopu ji nezmění (optional stopping). Změní se jen **tvar rozdělení**: méně výher, více malých ztrát a občas velký zisk.
2. **Na ES to potvrzují data.** Hrubá střední hodnota po všech schématech je +0,0 až +0,06R, tedy nula. Metoda z videa (S2) je horší než jedna pozice o 0,02–0,05R a po nákladech všude záporná (−0,12 až −0,24R).
3. **Úspěšnost klesne** z 31–36 % na 28–30 %, medián obchodu je −0,5R, 99. percentil 6,7–9,3R. Je to „flat, malý výherce, malý ztrátový nebo home run" přesně podle videa. Průměr se ale nezlepší.
4. **Pyramiding je dobrý jako disciplína** (nejhorší případ po přidání je zisk nebo malá ztráta, hlava se nerozpadne), ne jako edge. Skutečný edge musí přijít ze vstupu, a ten na ES z videa nemáme.

## Test
- ES 1min 2008–2026, jen RTH (9:30–16:00 ET), riziko R = 0,10 / 0,20 / 0,30 denního ATR; náklad 0,5 b. na kontrakt a otočení; stop se kontroluje před přidáním.
- **Vstupy** (3): (a) náhodný čas 10:00–14:00 (dlouhý i krátký zvlášť, jako kontrola), (b) průraz opening range (prvních 30 min) po směru i proti (fade), (c) „fashionably late" z videa: EMA9 přejde přes VWAP po pohybu ≥ 0,3 ATR od extrému dne, stop = 1/3 pohybu, cíl = celý pohyb (po směru i proti).
- **Schémata** (6): S0 jedna pozice se stopem −1R do konce dne; S1 stop −1R / cíl +3R; **S2 pyramid podle videa** (přidání po +1R, +2R, +3R, velikosti 0,5R / 0,25R / 0,125R vzhledem ke stopu přidání, stop celé pozice na předchozí úroveň, první přidání = breakeven); S3 pyramid stejných velikostí (to, co video označuje za chybu); S4 jako S2 s krokem 2R; S5 průměrování ztráty (přidání při −0,4R a −0,7R).
- 4 549–4 574 obchodů na variantu (2 588 u „late"), 336 řádků výsledků, 3 období, klastry po týdnech.

## Výsledky (riziko 0,2 ATR, průměr přes strany; `out/pyr_results.csv`)
| Vstup | Schéma | Hrubě R | Čistě R | Úspěšnost | 99. perc. R | Průměrná velikost |
|---|---|---|---|---|---|---|
| náhodný | S0 | +0,016 | −0,088 | 35,6 % | 5,8 | 1,00 |
| náhodný | S2 video | −0,007 | −0,141 | 30,4 % | 6,7 | 1,28 |
| náhodný | S3 stejné | −0,010 | −0,190 | 23,7 % | 11,2 | 1,71 |
| náhodný | S5 průměrování | +0,040 | −0,214 | 38,7 % | 11,1 | 2,43 |
| ORB | S0 | +0,032 | −0,072 | 31,1 % | 6,6 | 1,00 |
| ORB | S2 video | +0,017 | −0,121 | 27,7 % | 8,1 | 1,32 |
| ORB | S5 průměrování | +0,090 | −0,176 | 32,8 % | 13,4 | 2,53 |
| late | S0 | +0,027 | −0,145 | 24,3 % | 9,6 | 1,00 |
| late | S2 video | −0,015 | −0,243 | 25,8 % | 9,3 | 1,32 |
| late | S5 průměrování | +0,059 | −0,370 | 25,3 % | 18,0 | 2,50 |

- **Pokračování po +1R:** když cena dojde na +1R, pravděpodobnost dalšího +1R před návratem na vstup je při riziku 0,1 ATR 49,1 % (náhodný long), 46,9 % (náhodný short), 47,4 % (ORB po směru) a 47,1 % (ORB proti), při náhodné procházce 50 %. Stejné ve směru i proti, tedy žádné pokračování (u větších R vychází nižší jen kvůli konci dne). Soubor `out/cont_race.csv`.
- **Období:** u náhodných vstupů hrubě +0,01 (2008–15), +0,01 (2016–20), +0,03 (2021–26); S2 je ve všech dvou prvních obdobích horší než S0. Jediný rozdíl, který vydrží, je růst trhu (drift).
- **Jediný náznak:** „fashionably late" po směru má hrubě +0,03 / +0,08 / +0,10R ve třech obdobích, proti směru −0,06 / −0,02 / +0,05. Celkem +0,07R, t asi 1,5, tedy nevýznamné, a po nákladech −0,1R, protože stop je malý (R ≥ 0,1 ATR) a náklad tvoří 0,1R i víc.
- **Průměrování ztráty (S5)** má nejvyšší hrubou hodnotu (+0,04 až +0,18R) jen proto, že zvětšuje velikost při driftu. Po nákladech je nejhorší (−0,21 až −0,48R), úspěšnost 33 % a velké ztráty (medián −1,9R).

## Proč to nemůže vytvořit edge a kde pomáhá
- **Matematika:** pro martingale je střední hodnota součtu stop-time zisků nula. Přidání je nový obchod s nulovou hodnotou. S driftem trhu (ES roste) přidáváš velikost v rostoucím trhu, což je jen větší beta, ne alfa.
- **Pomáhá pouze, pokud:** (a) cena má skutečné trendové pokračování (na ES v testovaných vstupech ne), nebo (b) chceš **tvar výplaty** (konvexita: malé ztráty, občas 10–20R) a umíš ho unést. Pak se vyplatí S2 před S3.
- **Co z textu vzít použitelně:**
  1. Počítat vše v R a mít **součet rizika pozice** vždy před kliknutím (jako limit v algoritmu).
  2. Přidávat jen po **nezávisle platném signálu** na vlastní úrovni a s vlastním stopem; velikost přidání ≤ 0,5 předchozí.
  3. Po přidání **posunout stop celé pozice**, aby součet rizika klesl. Test: nikdy nesmí nárůst rizika.
  4. **Nepřikupovat při ztrátě** (S5): v testu je nejhorší schéma po nákladech, ruší to disciplínu.
  5. Zisk není polštář: velké přidání po +3R vymaže zisk (S3: úspěšnost 19–24 %, čistě −0,17 až −0,34R).
- **Jak to spojit s naším jediným reálným signálem** (slabost/přeprodanost → long na další noc/den, viz ZAVERY 20): pyramiding po signálu nepomůže (je to protisměrný vstup, ne trend). Co funguje je opačná pyramida podle síly signálu (vyšší skóre = větší velikost, ZAVERY 18 a 20), tedy sizing podle pravděpodobnosti, ne podle ceny po vstupu. Pyramiding podle videa nechat jen jako pravidlo, kdy lze po triggeru přidat při potvrzeném pohybu a se součtem rizika pod limitem.

## Omezení
- Vstupy z videa jsou jen jedna interpretace (ORB, EMA9/VWAP „fashionably late"); intraday akcie typu AMD/CBRS jsou jiný trh než ES, kde se trendové dny a likvidita chovají jinak.
- 1min data: pořadí high a low v minutě neznáme (stop se kontroluje první).
- Konec dne uzavírá pozici (bez držení přes noc).

Soubory: `pyr.py` (simulace), `out/pyr_results.csv`, `out/cont_race.csv`, `out/charts/schemata.png`.
