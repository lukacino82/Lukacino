# Jak na ES najít dlouhodobou hranu a generovat alfu

Shrnutí všech testů v tomto repozitáři (ES 07/2016–07/2026, volume bary, back-adjustované;
1min ES 2018–2026; náklady 0,5 b. na obchod). Nejdřív metoda, potom co data ukázala,
nakonec dva způsoby, jak z toho postavit portfolio: konzervativní a agresivní.

---

## 1. Matematika: co je hrana a kdy je skutečná

**Očekávaná hodnota obchodu** (v bodech nebo v R):

    E = p · W − (1 − p) · L − c

p = úspěšnost, W = průměrná výhra, L = průměrná ztráta, c = náklady.
Pro pevné TP/SL: **nutná úspěšnost = (SL + c) / (TP + SL)**.

**Past, na kterou narážely skoro všechny testy:** u ceny, která se chová náhodně, je
P(TP dřív než SL) = SL / (TP + SL) pro *jakékoli* TP a SL. Změna TP, SL nebo RRR mění
úspěšnost a velikost výher, ale **E zůstává nula minus náklady**. Hranu nevytvoří
výstup, jen **vstup**, po kterém cena nechodí náhodně.

**Hrana ≠ zisk.** ES za 10 let vyrostl z ~2 900 na ~7 800 bodů. Každý long vydělá.
Alfa = výsledek **nad** stejnými pravidly s náhodným vstupem (stejný směr, stejné
SL/TP, stejná délka držení). To je jediné poctivé měřítko.

**Statistická průkaznost:**

    t = průměr / směr. odchylka × √N          (chceme t ≥ 2, ideálně ≥ 3)
    N potřebné pro t = 2:  N = (2 · σ / μ)²

Obchod s +0,1 R a σ = 1 R potřebuje 400 obchodů, s +0,05 R 1 600 obchodů.

**Vícenásobné testování:** z M vyzkoušených variant vyjde ta nejlepší náhodou zhruba
s t ≈ √(2 · ln M). Při 100 variantách je to t ≈ 3,0, při 1 000 t ≈ 3,7. Náš test
1 776 vzorců to potvrdil: z top 30 bylo kladných mimo vzorek jen 47 %, tedy náhoda.

---

## 2. Protokol (pořadí je důležité)

1. **Hypotéza z mechanismu, ne z grafu.** Kdo je na druhé straně a proč prodělává?
   (nucené výprodeje, poskytování likvidity, riziková prémie, zajišťování dealerů).
2. **Zamknout data mimo vzorek** (např. posledních 30–40 %) předem. Hledá se jen ve
   vzorku.
3. **Málo parametrů, kulaté hodnoty.** Každý parametr navíc zvyšuje M.
4. **Plató, ne vrchol:** sousední hodnoty parametrů musí být také kladné.
5. **Benchmark náhodným vstupem** se stejnými pravidly (≥ 30 opakování), p-hodnota.
6. **Náklady a skluz** realisticky (ES 0,5 b. na obchod, víc u stop orderů a v noci).
7. **Mimo vzorek + walk-forward** bez jakékoli úpravy. Kladné roky ≥ 70 %.
8. **Paper / sim 3–6 měsíců se zmrazenými parametry**, pak malá live pozice (MES).
9. **Průběžná kontrola:** když se živé výsledky odchýlí o víc než 2 σ od testu, stop.

---

## 3. Co data ES ukázala

### Nefunguje (hranu nemá, nebo ji nejde odlišit od driftu)

| Test | Výsledek |
|---|---|
| Open ± X (fade i momentum), 96 kombinací X × RRR | žádné t > 1, TP % = break-even ± 6 b.b. |
| Open ± k·ATR, TP/SL podle ATR, 72 kombinací | žádné t > 1 |
| Long open+10/15, SL 20, RRR 2–3, drží do TP/SL | zisk = náhodný long (drift) |
| Vysoké RRR 10–20 : 1, 144 variant | TP % o 0–3 b.b. nad break-even, stejně jako náhoda; série 30–78 ztrát |
| RRR 1,5 : 1, 64 variant | long SL 10–20 b. = náhodný long, short ztrátový |
| TP/SL podle roku (walk-forward) | vrátí 5–20 % zpětně nejlepšího, horší než pevné 20/40 |
| ORB 5/15/30 min, Europe/Asia breakout, intradenní momentum | po nákladech ≈ 0 |
| Pattern mining 1 776 vzorců | top vzorce se mimo vzorek rozpadly (47 % kladných) |
| Shorty obecně | v rostoucím indexu ztrátové |

### Funguje (kladné i mimo vzorek, poráží náhodný vstup)

| Hrana | Obchodů | Na obchod | t | Kladné roky | Mechanismus |
|---|---|---|---|---|---|
| **Close pod VAL → long do close nad POC** (max 10 dní) | 210 | **+23,4 b.**, win 83 % | **4,4** | 7/9 | nákup pod hodnotou |
| **RSI(2) < 10 nad MA200, výstup close > MA5** | 72 | +28,9 b. | 2,6 | 7/8 | nucené výprodeje se vrací; parametry z r. 2008 = skutečně mimo vzorek |
| Close pod VAL → long 1–10 dní (pevně) | 348 | +9,2 b. (1 den) | 3,0–4,9 | 8/9 | totéž |
| Gap fade s potvrzením do 10:00, RRR 2 | 613 | +0,13 R | 2,5 | 8/9 | přestřelení na openu |
| Nákup po silném poklesovém dni (limit open − 0,25 ATR) | 375 | OOS t 0,88 | – | 9/11 nad bází | totéž, slabší |
| Noční držení jen nad MA200 | 1 525 | +1,5 b. | 2,3 | 6/8 | noční riziková prémie |

**Společný jmenovatel:** všechny robustní hrany jsou **nákup krátkodobé slabosti v trhu
s dlouhodobým růstem** (poskytování likvidity) a jsou swingové (1–10 dní), ne
intradenní. Nic, co kupuje sílu nebo shortuje, mimo vzorek nevydrželo.

---

## 4. Jak z hrany udělat výnos: velikost pozice

Sklon equity křivky = **kvalita hrany (Sharpe) × páka**. Páka zvedá výnos i drawdown
ve stejném poměru. Sharpe zvednou jen **lepší a nekorelované hrany**.

**Kellyho kritérium** (podíl kapitálu na riziko):

    binárně:   f* = p − (1 − p) / b        (b = W / L)
    spojitě:   f* = μ / σ²                  (μ, σ výnosu na obchod v % kapitálu)
    růst:      g(f) ≈ μ·f − σ²·f² / 2

* **Poloviční Kelly** dává ~75 % maximálního růstu s polovičními výkyvy. Plný Kelly
  je na odhadnutých (přeceněných) číslech cesta k ruinování.
* **Velikost podle volatility:** kontraktů = riziko v $ / (SL v bodech × $/bod).
  SL a TP v násobcích ATR, aby 1 R znamenalo pořád stejné riziko.
* **Série ztrát:** nejdelší očekávaná série při N obchodech ≈ ln(N) / ln(1 / (1 − p)).
  Při p = 0,4 a 1 000 obchodech ~13 ztrát za sebou. Riziko na obchod × tato série =
  minimální drawdown, se kterým musíte počítat.
* **MES** (1/10 ES, $5/bod) pro jemné nastavení velikosti.

---

## 5. Konzervativní přístup: stabilní křivka, nízký drawdown

**Cíl:** max. drawdown ~10–15 %, kladná většina let, roční výnos 8–15 %.

1. **Jádro 2 hran se silným t:** close pod VAL → long do POC a RSI(2) nad MA200.
   Obě jsou long, swingové a v trhu jen ~15–25 % času.
2. **Filtr režimu:** obchodovat jen nad MA200 (chrání před medvědím trhem).
3. **Riziko 0,25–0,5 % kapitálu na obchod**, max. 1 pozice na signál, max. 2 současně.
4. **Katastrofický stop** (např. 2–3 × ATR) jen proti krachu, ne jako řízení obchodu
   (testy ukázaly, že těsný SL tyto hrany ničí).
5. **Nečinnost je v pořádku:** mimo signál žádný obchod. Žádné open ± X.
6. **Pravidlo stop-loss pro systém:** při drawdownu 1,5 × horšího, než byl v testu,
   pozastavit a přezkoumat.

## 6. Agresivní přístup: strmá křivka

**Cíl:** strmější růst za cenu drawdownu 25–40 %. Stejné hrany, jiné řízení kapitálu.
Neznamená to „víc obchodů“ ani „vyšší RRR“ (obojí testy vyvrátily).

1. **Skládat nekorelované hrany:** VAL swing + RSI(2) + gap fade (intradenní) +
   noční držení nad MA200. Nízká korelace zvedá Sharpe portfolia, a tím i bezpečnou
   páku.
2. **Riziko 1–2 % na obchod**, poloviční Kelly jako strop. Pro VAL swing
   (win 83 %) vychází Kelly vysoko, ale kvůli chvostu (nejhorší obchod −379 b.) musí
   být strop na riziku krachu, ne na průměru.
3. **Volatility targeting:** držet stálou cílovou volatilitu portfolia (např. 20–25 %
   ročně). V klidných obdobích větší pozice, ve volatilních menší.
4. **Reinvestice (compounding)** místo fixní velikosti: velikost pozice roste
   s kapitálem.
5. **Pyramidování jen u swingových longů pod hodnotou** (přidat při druhém dni pod
   VAL), nikdy u intradenních signálů.
6. **Tvrdé brzdy:** při drawdownu −20 % riziko na polovinu, při −30 % na čtvrtinu.
   Bez nich agresivní přístup dříve či později skončí ruinou.

## 7. Co nedělat (potvrzeno daty)

* Hledat hranu v TP, SL nebo RRR. Rozhoduje vstup.
* Optimalizovat parametry podle roku nebo měsíce (walk-forward selhal).
* Věřit backtestu bez srovnání s náhodným vstupem (long v rostoucím trhu vydělá vždy).
* Vybírat nejlepší z desítek variant bez korekce na vícenásobné testování.
* Shortovat index bez velmi silného důvodu.
* Malé SL (2–5 b.): náklady tvoří 10–25 % rizika.

## 8. Další krok

Postavit Sierra studii pro **close pod VAL → long do POC** a **RSI(2) nad MA200**
(obě swingové, na denních datech, s ATR velikostí pozice), 3–6 měsíců sim se
zmrazenými parametry a srovnávat živé výsledky s čísly výše.

> Ani nejlepší hrana z těchto dat nezaručuje, že bude fungovat další desetiletí.
> Proto protokol v bodě 2 a průběžná kontrola v bodě 9 nejsou volitelné.
