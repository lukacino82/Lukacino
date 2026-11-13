# Inducement / sweep likvidity – má metodika z videa potenciál na datech ES?

**Otázka:** Video tvrdí, že průraz koncentrované likvidity (PDH/PDL, Asia H/L, týdenní/měsíční extrémy, equal highs/lows) v klíčových časech seance vybere stopy, nalákne obchodníky a cena se pak obrátí. Reverzní vstup po návratu pod/nad úroveň má mít edge. Platí to na ES 2008–2026?

## Jak jsem metodiku převedl na testovatelná pravidla
- **8 typů úrovní** (vysoké i nízké): předchozí den, týden, měsíc, 5denní a 20denní extrém, Asie, Evropa, noc (Globex). Všechny známé před průrazem.
- **Průraz** = první překročení úrovně o ≥ 0,03 ATR. Vzniklo 24 037 událostí.
- **Časová okna:** Asie, Frankfurt, Londýn, pre-NY, NY open, poledne, odpoledne.
- **A) Závod po průrazu:** který okraj padne první, návrat o D (0,1 / 0,2 / 0,4 ATR) nebo pokračování o D. Náhoda = 50 %.
- **B) Reverzní obchod** (to, co video učí): po návratu zpět za úroveň (do 10 / 30 / 60 min) vstup proti průrazu, stop za extrém, cíl 1R / 2R / 3R. Filtr rozumného rizika 0,03–0,6 ATR. Náklad 0,5 b.
- **C) Obchod po akceptaci** (průraz je skutečný, vstup po něm).
- **Kontrola:** placebo úrovně (stejné rozdělení vzdáleností od ceny, ale bez významu, 3 sady). Rozdělení na 3 období, klastry po týdnech.
- Neumím otestovat: footprint/absorpci, „kdo je v pasti" podle skutečných pozic, pojmy minor/medium/major (nejsou definované). Zkoušel jsem nahradit konfluencí úrovní, objemem a trendem.

## Výsledky
1. **Selhání průrazu je náhoda.** Po průrazu se cena vrátí první ve **49,4–51,1 %** případů podle vzdálenosti (placebo úrovně 50,9–51,9 %). Skutečné úrovně jsou **o 0–2 p. b. méně** návratové než náhodné, ne víc. Nic podobného „pasti" v datech není (`out/A_race_total.csv`, `charts/zavod_selhani.png`).
2. **Podle typu úrovně:** týdenní/měsíční vycházejí „nejlépe" (měsíční 42,9 % selhání, tedy průraz pokračuje častěji), jen 731 událostí. Žádný typ nemá selhání výrazně nad 50 % (max 51,3 % Asie).
3. **Podle okna:** Asie a Frankfurt +0,9 p. b. proti placebu, NY open až odpoledne záporně. Nejvyšší hodnota 52,8 % (559 událostí, t pod 2).
4. **Reverzní obchod (jádro metodiky): 0 ze 72 konfigurací je kladných po nákladech.** Průměr −0,19R (placebo −0,24R). Úspěšnost 31,0 % (R 2) oproti nulové 33,3 %. **Před náklady vychází +0,002 až +0,008R, tedy nula.** Průměrné riziko 4,8 b., náklad 0,5 b. = ~0,10R na obchod, takže trh je náhodná procházka a náklad rozhoduje (`out/B_trade_cfg.csv`).
5. **Stabilita v obdobích:** 2008–15 −0,25R, 2016–20 −0,13R, 2021–26 −0,10R. V žádném období kladný výsledek.
6. **Plošný sken 153 kombinací** (typ × okno × W × R, ≥ 300 obchodů): **žádná nemá t > 2, 86 % má t < −2** (placebo 95 %). Nejlepší kapsa: předchozí den v Asii (R 3, t 1,9, +0,15R, 541 obchodů) – to je maximum z 153, tedy očekávatelná náhoda.
7. **Obchod po akceptaci** (průraz bereš vážně): −0,08 až −0,13R. Taky záporné.
8. **Kvalifikátory z videa** (konfluence úrovní, objem, trend): úspěšnost se mění o ±2 p. b. bez monotónního vztahu, vždy záporné R. Objem 4× a víc: 31,4 %; konfluence 3+: 28,9 %.

## Verdikt
**Metodika na našich datech edge nemá.** Průraz úrovně není předvídatelný past: návratnost je 50 % jako náhoda, reverzní obchod je před náklady nula a po nákladech −0,1 až −0,2R. Jediný drobný rozdíl proti placebu je, že skutečné úrovně jsou o ~0,05R lepší než nesmyslné (úrovně mají mikrostrukturní význam), ale ne tak, aby to pokrylo náklad.

Možné vysvětlení rozporu s videem: (a) survivor bias (ukázané příklady jsou vybrané), (b) „kontrola", footprint a ruční výběr „správného" inducementu jsou neměřitelné a subjektivní, (c) video je marketing kurzu. Pokud někdo dokáže pravidla zapsat bez dodatečného výběru, jdou testovat stejně jako výše.

**Co z toho ještě stojí za prověření:** nic z tohoto směru. Použitelný signál z dřívějšího výzkumu zůstává slabost/přeprodanost → long přes noc/další den (viz ZAVERY 20), tohle ho nepotvrzuje ani nezlepšuje.

Soubory: `idm.py` (sestavení), `analyze.py`, `charts.py`, `out/*.csv`, `out/charts/*.png`.
