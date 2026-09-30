# Co ještě doladit ve skriptu

Audit k 30. 9. 2026, po Replay testu. Odpovídá na dvě otázky: jsou nové materiály
(`SWING_ALPHA_BRAINSTORM.txt`, `README_SIERRA_ES2008_SWING_ALPHA.md`,
`ES2008_LOWER_CLOSE_VWAP_MASTER_REPORT.html`) použitelné, a co ve studii chybí.

Všechna čísla níže jsou spočítaná z `ES2008.txt` v repu (6 439 576 minutových řádků,
2008-05 až 2026-09). Přepočítat je jde `python swing_lab/verify_new_ideas.py` — postup
rozbalení archivu je v hlavičce skriptu. Buy & hold na tomhle datasetu je **5 757,25 bodu**,
což je přesně číslo z reportu, takže srovnáváme totéž.

---

## 1. Nové materiály: co z toho obstojí

### Reprodukce sedí

Systémy z reportu jsem dopočítal znovu a čísla vycházejí prakticky na kus: S10 385 obchodů
a 5 208 bodů (report 385 / 5 207,5), S11 173 a 4 276 (report 173 / 4 279,25), S20 51 obchodů
(report 51), S30 21 obchodů (report 21), 3 lower closes 127 epizod (report 127). Takže se
nebavíme o jiné metodice — počítáme totéž, co report.

### Chybí jim jediné srovnání, na kterém záleží

Report nikde neporovnává systém s tím, co udělá **držení stejného instrumentu stejně dlouho**.
U long-only systému na indexu, který dlouhodobě roste, je tohle jediný smysluplný benchmark.
Placebo test: stejný počet vstupů, stejná doba držení, ale **vstupní dny vybrané náhodně**,
10 000 opakování.

| Systém | n | Body | PF | WR | Náhodné vstupy, medián | p |
|---|---:|---:|---:|---:|---:|---:|
| S01 streak 3–6 + bull + < dVWAP, hold 20 | 84 | 1 900 | 1,60 | 64,3 % | 1 960 | **0,52** |
| S10 close < daily VWAP, hold 10 | 385 | 5 208 | 1,57 | 67,0 % | 4 156 | **0,29** |
| S11 < daily VWAP + > MA200, hold 20 | 173 | 4 276 | 1,97 | 65,9 % | 3 937 | **0,42** |
| S20 weekly < wVWAP + MA40, hold 65 | 51 | 4 327 | 2,96 | 74,5 % | 3 957 | **0,40** |
| S30 monthly < mVWAP + MA10, hold 126 | 21 | 4 856 | 19,41 | 90,5 % | 3 225 | **0,12** |
| exact 3 lower closes, hold 20 | 127 | 2 074 | 1,37 | 59,8 % | 2 871 | **0,70** |
| exact 4 lower closes, hold 20 | 78 | 2 727 | 1,86 | 62,8 % | 1 862 | **0,21** |

**Ani jeden nemá p pod 0,10.** Náhodně vybrané dny se stejnou dobou držení dopadnou stejně
nebo líp ve 12 až 70 % případů. Ten slavný monthly systém se 100% úspěšností a „98,25 %
buy & holdu" není dovednost: držet ES libovolných 126 seancí vyjde kladně v 77,3 % případů
a vydělá průměrně 154 bodů. Filtr na monthly VWAP to posune na 90 % a 231 bodů — a to je
přesně v pásmu, které vyrobí náhoda.

### U lower-close systémů je navíc look-ahead

Report definuje signál jako *exact finalized streak* — maximální série právě k nižších close.
Že série skončila u tří, se ale pozná **až když čtvrtý den zavře výš**. Vstup „next RTH open"
ráno po třetím dni tedy používá close, který ještě neexistuje. Pustil jsem obě čtení:

| | n | Body | Na obchod | PF | WR |
|---|---:|---:|---:|---:|---:|
| 3 lower, SL 20 b. — jak je v reportu | 123 | 1 806 | **+14,69** | 2,45 | **51,2 %** |
| 3 lower, SL 20 b. — až po potvrzujícím close | 108 | −321 | **−2,97** | 0,79 | 37,0 % |
| 4 lower, SL 10 b. — jak je v reportu | 60 | 759 | +12,65 | 2,56 | 26,7 % |
| 4 lower, SL 10 b. — až po potvrzujícím close | 58 | −66 | −1,13 | 0,86 | 22,4 % |
| 5 lower, SL 15 b. — jak je v reportu | 26 | 254 | +9,79 | 1,82 | **34,6 %** |
| 5 lower, SL 15 b. — až po potvrzujícím close | 24 | −176 | −7,33 | 0,49 | 12,5 % |

Report uvádí pro 3 lower / SL 20 úspěšnost **51,2 %** a pro 5 lower / SL 15 **34,62 %** —
tedy přesně první řádek každé dvojice, na desetinu. Měřil tu variantu, která se obchodovat
nedá. Obchodovatelná verze je u všech tří záporná.

### Co z toho zbývá

Jedna věc. Série nižších close **bez** podmínky maximality (`downdays >= 3`, což se ví hned
na close) s těsným stopem a targetem na předstřakovém close dá 1,35 až 2,28 bodu na den
v trhu proti 1,21 u buy & holdu. Expozice je ale jen kolem 6 %, takže to není náhrada
indexu, jen overlay. A tuhle rodinu už náš vlastní výzkum sítem hnal, ve dvou variantách:

| Rodina | Konfigurací | alfa t | Porazila B&H | Kde skončila |
|---|---:|---:|---|---|
| `DownDays>=#` — holá série nižších close | 2 280 | — | — | vypadla už v předvýběru |
| `LMT_Down#_#ATR` — limitní vstup po sérii | 1 140 | **1,72** | **ne** | došla do finále, neprošla prahem 2 |
| `LMT_RSI#<#_#ATR` — limitní vstup na RSI | 8 280 | **3,03** | **ano** | **je ve studii, 4 presety** |

Limitní vstup po nižších close je tedy nejbližší příbuzný toho nového nápadu a **prošel až
do finálního kola** — s alfou t 1,72 a bez toho, aby porazil buy & hold. Ve studii je místo
něj varianta, která totéž dělá přes RSI a má t 3,03. To není náhoda ani opomenutí: ta série
sama o sobě nese míň informace než oscilátor na stejném místě.

**Závěr: z nových materiálů nevzniká nová strategie.** Architektonické části
(`README_SIERRA_ES2008_SWING_ALPHA.md` — pořadí zpracování, parity logging, production gate)
popisují to, co studie dělá, a to jsme si Replayem právě ověřili.

### Kde reálně stojíme

Náš vlastní koš 48 presetů, spočítáno z `sierra/reference_journal.csv` na okně
2015-10 až 2026-09:

| | |
|---|---:|
| P&L knihy | 73 029 bodů / 6 504 obchodů |
| Průměrná souběžná expozice | 12,05 kontraktu |
| Na 1 kontrakt-ekvivalent | 6 061 bodů |
| Buy & hold za stejné období | 4 945 bodů |
| **Poměr na jednotku kapitálu a času** | **1,23×** |

To je skutečná, i když skromná převaha, a sedí s vol-matched číslem z `swing_lab/README.md`
(CAGR 12,95 % proti 9,66 %). Slepý test tam ale dává alfa t = 1,33 proti prahu 2 — pořád
kandidát na paper-forward, ne na ostrý účet.

---

## 2. TP / SL / RRR: už přednastavené jsou

Každý z 48 presetů si nese vlastní exit model ve sloupci `exit` v `swing_presets.csv`.
**41 různých exitů na 48 presetů**, 20 z nich je bracket se SL a RRR, 8 posouvá stop
(trailing nebo breakeven), zbytek jsou signálové výstupy typu „zavři na RSI2 > 70".
Nejsou to výchozí hodnoty — je to výsledek testu, který pro ten konkrétní preset prošel.

**Měnit je jde už teď, bez zásahu do DLL:** přepiš sloupec `exit` v CSV a přepni Input 5
*Reload Presets*. Parser rozumí těmhle tokenům (`ParseExit`, `Lukacino_MultiSwing.cpp:336`):

```
SL1.5ATR_RRR2.0            stop 1,5 × ATR20, target 2 × riziko
SL1.0ATR_RRR3.0_BE1.0R     totéž + breakeven po 1R
SL3.0ATR                   jen katastrofický stop
Trail1.0ATR_act1.0R_T20    trailing 1 ATR, aktivace na 1R, časový stop 20 seancí
C>SMA5+SL2.0ATR+T10        výstup na close nad SMA5, plus stop a čas
IBS>0.8 / RSI2>70 / C>PrevHigh / C>wvwap / FirstUpClose / Time15
```

Co **nejde** a co bys pro nové nápady potřeboval, je níže jako P4 a P5.

---

## 3. Co ve skriptu chybí, podle priority

### P1 — Posuny stopu se do Sierry nepřenášejí

Bracket se nastaví při vstupu a už se nemění. 8 ze 48 presetů ale stop posouvá, což je
**304 obchodů ze 6 504 (4,7 %)**. Na účtu skončí tržním příkazem místo na posunutém stopu:
horší cena, systematicky v neprospěch. Není to díra v riziku — pozice zůstává chráněná
původním, širším stopem.

Oprava je `sc.ModifyOrder` na připojený stop. Potřebuju k tomu ověřit přesné názvy členů
ACSIL; egress z kontejneru sierrachart.com nepustí. **Zkopíruj mi sem stránku *ACSIL Trading
Functions*, sekci k připojeným příkazům, a dopíšu to.**

### ~~P2 — kill switche~~ HOTOVO 30. 9.

Inputy 38 *Daily Loss Limit* a 39 *Max Drawdown Stop* fungují, počítané z vlastního ledgeru
studie (žádné čtení účtu). Podrobnosti a cena v `NASTAVENI.md`, kapitola 5. Zbývající mrtvé
Inputy jsou 40, 41 (Scale In) a 45 (Max Slippage); 46 musí zůstat No tak jako tak.

### ~~P3 — override per rodinu~~ HOTOVO 30. 9.

Inputy 65–88, dvojice SL / RRR na rodinu, nula = nech preset být. Ověřeno regresí na
4 122 506 barech: s výchozími hodnotami je ledger bit-identický s předchozí verzí.

### P0 (nové, 30. 9.) — nekompletní seance

Replay 2016–2026 měl 99,7 % P&L a 34/48 presetů s identickou množinou vstupů. **Všech 26
rozdílných vstupů leželo na pěti dnech v srpnu 2023** a měly jednu příčinu: seance
2023-08-09 skončila v replayi v 15:35 místo v 16:00, takže close byl 5268,00 místo 5249,25.
Ten špatný close pak šel do ATR20 a klouzavých průměrů na dalších dvacet seancí.

Studie to teď pozná a nahlásí (`INCOMPLETE SESSION` v logu, počítadlo ve status boxu),
plánované půldny odliší podle času — ověřeno na 99 zkrácených seancích z let 2015–2026,
nula falešných poplachů. `check_replay.py` navíc rozdíly shlukuje podle dnů a na tenhle
vzorec sám upozorní.

**Sama data to neopraví.** Když replay zastavíš uprostřed seance, ten úsek pusť znovu.

### P2b — zbylé mrtvé Inputy

Nejsou to zapomenuté nuly, ta logika neexistuje:

| # | Input | Dopad |
|---|---|---|
| 45 | Max Slippage ticks | fill za libovolnou cenu projde |
| 40, 41 | Scale In / Cap | funkce ze zadání, není |
| 46 | Flatten At Session End | musí zůstat No (swingy), takže neškodí |

Max Slippage má smysl až u živých fillů; na Simu je slippage stejně simulovaný.

### P3 — Exit override je globální, ne per systém

Input 52 přepíše TP/SL/RRR **všem 48 presetům naráz**. To je to, na co se ptáš: nastavit
TP/SL/RRR u každého systému zvlášť dnes jde jen přes CSV, ne přes Inputy.

Rozpočet na to je: studie používá 65 Inputů z limitu 128, volných je **63**. Návrh, který
se vejde a nerozbije číslování (nové indexy jen na konec, existující nepřečíslovávat):

```
65..88   dvojice na rodinu: "Fam<k> Override SL (x ATR, 0 = použij preset)"
                            "Fam<k> Override RRR (0 = použij preset)"
```

24 Inputů, celkem 89, rezerva 39. Nula znamená „nesahej", takže výchozí chování zůstane
přesně to ověřené. Per preset už by se to nevešlo (48 × 2 = 96) a stejně patří do CSV.

### P4 — Exit jazyk neumí body a ticky

`ParseExit` zná jen ATR násobky. Nové nápady stojí na **pevných bodových stopech**
(20 bodů, 10 bodů, 150 bodů) a ty v CSV nezapíšeš. Globální override je v ticích umí
(Inputy 55/56), per preset ne. Doplnit `SL20pt_RRR2.0` a `SL20pt_TP80pt` je zásah
do jedné funkce.

Než to uděláš, vezmi v úvahu bod 4 ze závěrů v `swing_lab/README.md`: *„Pevné body TP/SL
se mimo vzorek rozpadají, používat ATR."* Výsledky z části 1 to potvrzují — obchodovatelná
verze pevných stopů je u všech tří variant záporná.

### P5 — Není cílová cena typu „návrat na hladinu"

Target je dnes vždycky `tpAtr` od vstupu. Nové materiály staví na targetu
= **close před začátkem série**, tedy na absolutní hladině. To je nový druh exitu
(`XS_` kind + pole na cenu), ne parametr. Dělal bych to jen tehdy, kdyby to prošlo
sítem — podle části 1 neprošlo.

### P6 — Chybí long core

`grep -ci "core"` ve studii vrací 0. Přitom vlastní závěr výzkumu, dvakrát zopakovaný
v brainstormu, zní: **dlouhodobé long jádro + swing overlay**, a měřit
`R(core+overlay) − R(core)`. Studie implementuje jen overlay. Dokud jádro chybí, neměříš
to, co jsi chtěl měřit — a 1,23× z části 1 je poměr na jednotku expozice, ne alfa nad
jádrem. Jeden preset s `role = R0 core`, který drží 1 kontrakt trvale, by to uzavřel.

Tohle je z celého seznamu ta nejvíc strategická věc, ne ta nejvíc urgentní.

### P7 — Dojet Replay 2020–2026

Není to zásah do skriptu. Ověřeno máme 2016-08 → 2019-12 se 100% shodou po zahřátí;
covid, 2022 a poslední roky ověřené nejsou.

### P8 — Shorty nejsou a nebudou

Všech 6 504 obchodů v referenci je long. Input 3 *Direction Filter* umí *Both* i *Short only*,
ale žádný preset short nemá. Výzkum: shorty na ES nefungují. Input nechávej na *Long only*,
jinak jen mate.

---

## Stav k 30. 9.

| | |
|---|---|
| ~~P2 kill switche~~ | hotovo |
| ~~P3 override per rodinu~~ | hotovo |
| ~~P0 nekompletní seance~~ | detekce hotová |
| ~~P7 dojet Replay~~ | hotovo, 99,7 % na 2016–2026 |
| **P1 posuny stopu do Sierry** | **jediná věc, která brání plnému full auto** — čeká na dokumentaci ACSIL |
| P6 long core | strategické, až se rozhodneš měřit overlay proti jádru |
| P2b, P4, P5 | nedělat, dokud nebude co implementovat |

Pro full auto na Simu je hotovo všechno kromě P1. Ten není blokující v tom smyslu, že by
se nedalo obchodovat — 8 ze 48 presetů skončí tržním příkazem místo na posunutém stopu,
což je 4,7 % obchodů za horší cenu, ne nechráněná pozice.
