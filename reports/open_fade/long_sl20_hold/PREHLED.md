# Jen LONG, SL 20 b., RRR 2:1 / 3:1: s výstupem v 16:00 vs. držení do TP/SL

Data: váš Excel (back-adjustovaný kontinuální ES, 07/2016–07/2026), 1 ES,
náklady 0,5 b. na obchod. Vstup v RTH: long na open + X (stop order) nebo
na open − X (limitka), X = 10/15/20/30/40. SL 20 b., TP 40 b. (2:1) nebo
60 b. (3:1).

## A) Výstup nejpozději v 16:00 (`../long_sl20/`)

| Vstup | Nejlepší | t | Ostatní |
|---|---|---|---|
| open + X | X=20, 2:1: +$33,7k | 1,1 | X=15 +$33,0k, X=40 −$21,9k |
| open − X | X=20, 3:1: +$22,9k | 0,6 | X=15 2:1 −$53,2k |

Asi polovina obchodů skončí v 16:00 (ani TP, ani SL).

## B) Bez výstupu v 16:00: drží přes noc do TP/SL (tato složka)

| Vstup | RRR | X=10 | X=15 | X=20 | X=30 | X=40 |
|---|---|---|---|---|---|---|
| open + X | 2:1 | +$59,5k | **+$71,4k** | +$60,2k | +$28,1k | −$15,0k |
| open + X | 3:1 | **+$82,5k** | +$77,8k | +$35,1k | −$5,0k | −$11,7k |
| open − X | 2:1 | +$23,3k | +$11,3k | +$8,8k | −$75,2k | −$47,8k |
| open − X | 3:1 | +$52,0k | +$27,6k | +$39,6k | −$66,8k | −$52,0k |

Průměrné držení 12–42 h (medián 2–11 h), 27–50 % obchodů drží přes noc.
Nejlepší t = 1,6. Max. drawdown −$22k až −$85k.

## Kontrola: náhodný long se stejnými pravidly

Long v náhodném čase RTH (bez podmínky open ± X), SL 20, držení do TP/SL,
max. 1 pozice, 30 opakování:

| | Průměr | 5.–95. percentil |
|---|---|---|
| TP 40 / SL 20 | **+$81,7k** (1,16 b./obchod) | +$42,9k až +$146,7k |
| TP 60 / SL 20 | **+$94,3k** (1,59 b./obchod) | +$44,5k až +$159,1k |

**Náhodný vstup vydělá víc než nejlepší varianta systému** (+$71,4k,
resp. +$82,5k). Zisk bez výstupu v 16:00 pochází z držení longu v trhu,
který za 10 let vyrostl o ~4 900 bodů (noční drift), ne z podmínky
open ± X. Podmínka hranu nepřidává. Long na open − 30/40 je dokonce
výrazně horší než náhoda.

## Závěr

* Zrušení výstupu v 16:00 zlepší výsledek jen proto, že pozice sbírá
  růst trhu přes noc. Totéž udělá náhodný long.
* Jako samostatný edge to neobstojí. Kdo chce sbírat drift indexu, má
  jednodušší a levnější cestu (držet long / noční držení nad MA200,
  viz `reports/es_durable`).
* Pro skutečnou alfu musí vstup porazit náhodný vstup se stejnými
  pravidly, ne nulu.
