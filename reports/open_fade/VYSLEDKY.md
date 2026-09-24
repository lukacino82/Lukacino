# Open ± X: limitní vstup proti pohybu od RTH open

**Pravidla:** limitní long na open − X, limitní short na open + X (RTH open
09:30 ET). TP 60 ticků (15 b.), SL 40 ticků (10 b.), RRR 1,5:1, jinak výstup
na konci seance (16:00). Oba směry nezávisle, max. 1 obchod na směr a den.

**Data:** `es mini data new 2 (2).xlsx`, list `List1`: 761 361 volume barů
(5 000 kontraktů), 07/2016–07/2026, 2 491 RTH dní. Kontrolně i 1min ES
2018–2026 (2 046 dní) se shodným výsledkem.

Skript: `open_fade/open_fade.py` (čte .xlsx, .txt i .pkl).

## Kolikrát přijde TP dřív než SL (break-even = 40 %)

| X | Směr | Vstupů (% dní) | TP | SL | Konec seance | **TP % z TP+SL** | b./obchod hrubě | po nákl. 0,5 b. |
|---|---|---|---|---|---|---|---|---|
| 10 | long open−10 | 1 488 (60 %) | 485 | 809 | 194 | **37,5 %** | −0,10 | −0,60 |
| 10 | short open+10 | 1 523 (61 %) | 494 | 787 | 242 | **38,6 %** | −0,17 | −0,67 |
| 15 | long open−15 | 1 182 (47 %) | 393 | 663 | 126 | **37,2 %** | −0,32 | −0,82 |
| 15 | short open+15 | 1 181 (47 %) | 365 | 636 | 180 | **36,5 %** | −0,62 | −1,12 |
| 20 | long open−20 | 996 (40 %) | 352 | 553 | 91 | **38,9 %** | +0,05 | −0,45 |
| 20 | short open+20 | 961 (39 %) | 296 | 512 | 153 | **36,6 %** | −0,54 | −1,04 |
| 40 | long open−40 | 463 (19 %) | 171 | 250 | 42 | **40,6 %** | +0,32 | −0,18 |
| 40 | short open+40 | 391 (16 %) | 130 | 181 | 80 | **41,8 %** | +0,54 | +0,04 |

Oba směry dohromady po nákladech: X=10 −$95k, X=15 −$114k, X=20 −$73k,
X=40 −$3k (1 ES, 10 let). Nic není statisticky odlišné od nuly v kladném
směru. Nejlepší X=40 má t = 1,07 hrubě a −0,20 po nákladech.

## Proč: ES se na těchto úrovních chová jako náhoda

U náhodné procházky platí P(TP dřív než SL) = SL / (TP + SL). Pro 15/10 je
to **přesně 40 %**. Mřížka 6 poměrů TP/SL × 4 úrovně X
(`excel_mrizka_tp_sl.csv`) ukazuje, že skutečné TP % se vždy drží ±3
procentní body od této hodnoty. Změna RRR tedy mění jen win-rate, ne
hranu. Po nákladech je každá kombinace pro X = 10–30 ztrátová (t −1,8 až
−4,5).

**Pořadí v rámci baru výsledek neovlivňuje:** optimistická varianta (SL
i TP ve stejném baru = TP) dává shodná čísla, protože TP a SL jsou 25 b.
od sebe.

## Verdikt

Jako samostatný systém to nemá smysl. Není tu hrana, jen náhoda minus
náklady. Jediné místo mírně nad break-even je X = 40 (41–42 %), ale
s ~85 obchody ročně a t ≈ 1 to je statisticky šum a roky se střídají.

Pokud chcete fade od open dál rozvíjet, potřebuje **podmínku, která
náhodu naruší**. Jde o kontext, ne jiné TP/SL. Co jsme dosud změřili:
* gap fade s potvrzením do 10:00 (+0,13 R, t 2,5, viz `reports/es`),
* vstup jen, když delta nepotvrzuje pohyb (průraz proti CVD ztrácí,
  viz `reports/es_orderflow`),
* swing nákup pod value area (+23 b./obchod, t 4,4).
