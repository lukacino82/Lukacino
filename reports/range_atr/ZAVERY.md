# Denní rozpětí ES, Gaussova křivka a ATR: dá se z nich postavit edge?

Data: váš Excel, 2 491 RTH dní 07/2016–07/2026. Graf: `rozpeti_atr.png`.
Skripty: `range_atr/range_stats.py`, `atr_dynamic.py`, `plot_range.py`.

## 1. Rozdělení denního rozpětí (H−L, RTH)

| | Hodnota |
|---|---|
| průměr / medián | **45,2 / 36,8 bodu** (vaše 44,18 se liší jen definicí seance) |
| σ | 35,6 bodu |
| šikmost / špičatost | **3,1 / 24,8** (Gauss 0 / 0) |
| dní pod průměrem | **60,5 %** (1 507 dní) |
| dní nad průměrem | 39,5 % (984 dní) |

**Gaussova křivka sem nepatří.** Rozdělení je pravostranně zešikmené
(log-normální tvar): hodně klidných dní a dlouhý chvost extrémů.

| Pásmo | Skutečnost | Gauss |
|---|---|---|
| ±1σ (9,6–80,8 b.) | **83,1 %** (2 071 dní) | 68,3 % |
| nad +1σ (> 80,8 b.) | 12,2 % | 15,9 % |
| pod −1σ (< 9,6 b.) | 4,6 % | 15,9 % |
| nad +2σ (> 116 b.) | 4,0 % | 2,3 % |
| nad +3σ (> 152 b.) | **1,3 %** | 0,13 % (10× méně) |

Pásma: 0–20 b. 23,9 % · 20–30 15,4 % · 30–40 14,9 % · 40–50 12,3 % ·
50–60 9,0 % · 60–80 11,8 % · 80–100 6,1 % · 100–150 5,2 % · > 150 1,4 %.
Percentily: 10 % = 12,2 · 25 % = 20,8 · 50 % = 36,8 · 75 % = 59,5 ·
90 % = 87,0 · 95 % = 110,2 · 99 % = 157,3 b.

**Průměr 45 b. za celou historii je zavádějící.** Po letech je průměrné
rozpětí 13–74 bodů, protože roste s cenou (2 900 → 7 800) a s režimem
volatility (2020, 2022, 2025). Pevný TP/SL v bodech je v klidném roce moc
široký a ve volatilním moc úzký.

## 2. ATR: co umí a co ne

* **Umí předpovědět velikost dne.** ATR(14) z minulých dní vysvětlí 42 %
  rozpětí (korelace 0,65). Normované rozpětí (rozpětí/ATR) je mnohem
  stabilnější: medián 0,91×, 50 % dní mezi 0,67× a 1,24× ATR.
* **Neumí předpovědět směr.** Od open dojde cena aspoň 0,5×ATR nahoru ve
  40 % dní a dolů taky ve 40 %. Na 1×ATR nahoru 10 %, dolů 15 %.

## 3. Test: TP/SL dynamicky podle ATR

Open ± k×ATR (k = 0,25 / 0,5 / 0,75), SL = 0,25×ATR, TP podle RRR
1:1 / 1:1,5 / 2:1 / 3:1, momentum i fade, long/short, náklady 0,5 b.

* **72 kombinací, žádná nemá t > 1.** Oba směry dohromady jsou všude
  ztrátové (−0,04 až −0,13 R na obchod).
* Úspěšnost TP se znovu drží na break-even náhody (1:1 ~50 %, 2:1
  ~31 %, …).

## 4. Závěr: co je „optimální TP/SL“

**TP a SL hranu nevytvoří, ani pevné, ani podle ATR.** U náhodné ceny je
P(TP dřív než SL) = SL / (TP + SL) pro jakékoli nastavení. RRR jen mění
win-rate proti velikosti výher. Očekávaná hodnota zůstává nula minus
náklady. Hrana vzniká jen ve **vstupu**: v podmínce, po které cena
nechodí náhodně.

**ATR má smysl, ale na něco jiného:**
1. **Škálovat SL/TP podle volatility**, aby 1 R znamenalo pokaždé stejné
   riziko, ať je den klidný, nebo divoký.
2. **Velikost pozice = pevné $ riziko / (SL v bodech × $/bod)**. V
   divokých dnech menší pozice, v klidných větší. To snižuje drawdowny
   a zlepšuje poměr výnosu k riziku, ale jen u systému, který hranu už
   má.
3. **Filtr nákladů:** když je očekávané rozpětí malé, náklady tvoří
   velkou část R. Takové dny vynechat.

**Doporučený postup k alfě:**
vstup s prokázanou hranou (z našich testů: swing „close pod VAL → long“,
+23 b./obchod, t 4,4; gap fade t 2,5) + SL/TP a velikost pozice podle ATR
+ walk-forward ověření. To je pořadí: nejdřív edge, pak risk management.
