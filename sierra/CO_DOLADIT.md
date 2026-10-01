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

### ~~P1 — posuny stopu do Sierry~~ HOTOVO 30. 9.

Doděláno, jakmile přišly hlavičky z tvé instalace. Chybějící spojka byla
`sc.GetAttachedOrderIDsForParentOrder(parent, target, stop)` — z ID vstupu dá ID připojeného
stopu, ten se pak mění `sc.ModifyOrder` s `InternalOrderID` a `Price1`. Stop se posouvá **jen
nahoru**. Ověřeno na 4 122 506 barech: 643 posunů a přesně těch 8 presetů, které mají v CSV
`Trail` nebo `BE`. Podrobnosti v `README.md`, sekce *Co order vrstva zaručuje*.

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

### ~~P7 — dojet Replay 2020–2026~~ HOTOVO 30. 9.

99,7 % P&L na celém 2016–2026, a jediná odchylka měla jednu příčinu — viz P0 výš.

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
| ~~P1 posuny stopu do Sierry~~ | hotovo |
| ~~P9 dva ACSIL přepínače~~ | hotovo, ověřeno offline simulací příkazů |
| ~~P10 zapomenuté brackety + ratchet~~ | hotovo, ověřeno offline simulací příkazů |
| ~~P11 osiřelé pozice z předchozího běhu~~ | hotovo, studie odmítne obchodovat |
| **P12 odprodej přebytku** | **příčina potvrzena Sierrou, oprava rozpracovaná** |
| P6 long core | strategické, až se rozhodneš měřit overlay proti jádru |
| P2b, P4, P5 | nedělat, dokud nebude co implementovat |

**Pro full auto na Simu je hotovo všechno.** Order vrstva umí vstup s vlastním bracketem,
posun stopu podle trailu i breakevenu, srovnání pozice na konci seance a dva limity ztrát.
Co zbývá, je strategické (P6 long core), ne technické.

### P9 (nové, 30. 9.) — dva chybějící ACSIL přepínače. HOTOVO

Na grafu se v *Full auto* otevřel **jeden** kontrakt, kniha chtěla deset, a zbytek se odmítl.
Příčina nebyla v knize ani v účtu: Sierra má `sc.AllowEntryWithWorkingOrders` **defaultně
false**, takže každý vstup po prvním se odmítne, protože pracují stopy a targety těch
předchozích. A tahle kniha je právě to — mnoho bracketů na jedné netto pozici.

Druhý přepínač je nebezpečnější. Sierra sama radí zapnout
`sc.CancelAllOrdersOnEntriesAndReversals` při použití připojených příkazů, aby se při zmenšení
pozice zrušily připojené příkazy, které už neodpovídají. Ta rada je napsaná pro systém s
**jednou** pozicí. Tady odprodej přebytku zavírá jeden preset z deseti a „zruš všechny příkazy"
by sebralo stop zbývajícím devíti — kniha by je dál hlásila jako chráněné a nestálo by za nimi
nic. Nastaveno explicitně na `false`, ne ponecháno na defaultu.

Třetí věc, kterou ten rozbor našel: Max Gross se posílal do `sc.MaximumPositionAllowed`
nepřevedený, přitom se počítá v MES ekvivalentech a Sierřin strop v kontraktech obchodovaného
instrumentu. Na ES byl ten záchytný strop 10× volnější než strop knihy.

### Offline simulace příkazů (nové, 30. 9.)

`test_stub/sierrachart.h` s `STUB_ORDERS=sim` už není jen „všechno odmítni". Je to malá
knížka příkazů, která vynucuje stejná tři pravidla, jaká Sierra dokumentuje pro příkazy ze
studie, a drží každému vstupu jeho stop a target. **Netestuje Sierru** — testuje, že si studie
nevyžádá něco, co ta pravidla zakazují. Právě tohle se z kódu vyčíst nedalo.

Měřeno na 4 680 seancích, ES, risk unit 1, Max Gross 600:

| | před (`99543aa`) | po (`2026-09-30.13`) |
|---|---|---|
| vstupů přijato | **2** | **9 821** |
| odmítnuto kvůli pracujícím příkazům | **5** → `STOPPED` | **0** |
| odmítnuto kvůli stropu pozice | 0 | **0** |
| odprodej přebytku větší, než se drží | 0 | **0** |
| stopů zrušených odprodejem | 0 | **0** |
| posunů stopu / z toho na mrtvý příkaz | 0 / 0 | 1 171 / **0** |
| špička pozice vs. `MaximumPositionAllowed` | 2 / 600 | 60 / **60** |

`ES / cap 600` a `MES / cap 60` teď dávají **identické** číslo vstupů i špičku pozice. Před
opravou převodu se lišily.

Dvě věci k té simulaci na rovinu: neplní brackety (proto na konci „visí" 10 144 pracujících
příkazů) a běží na barech, jejichž denní OHLC a overnight extrémy jsou skutečné, ale
vnitrodenní cesta je dosyntetizovaná — pro test order vrstvy to je jedno, pro paritu
rozhodovacího jádra se používá jiný běh.

### P10 (nové, 30. 9.) — zapomenuté brackety a ratchet. HOTOVO

S opravenými přepínači prošlo všech 10 vstupů, ale **`SELL 9` na srovnání pozice padal na `-1`**,
a to v *grafové simulaci*, kde žádný účet není — takže to nemohlo být menu Trade.

Příčina: když kniha zavře preset vlastním důvodem (signálový exit, time stop), Sierra dál
pracuje stop a target, které s tím vstupem odešly. Nic jí neřekne, že preset skončil. Ty
příkazy zůstanou pracovat **natrvalo**, jejich množství se počítá proti pozici — a tržní prodej
přebytku je pak z Sierřina pohledu přeprodej. Sierřina vlastní rada na tohle je
`CancelAllOrdersOnEntriesAndReversals = true`, což by ale sebralo stop všem ostatním presetům.
Správné řešení je zrušit brackety **jen těch presetů, které kniha zavřela**
(`GetAttachedOrderIDsForParentOrder` + `CancelOrder`), a nic jiného.

To samo je vážná chyba i bez toho `-1`: zapomenutý bracket zavřeného presetu se někdy vyplní a
posune pozici za zády knihy.

Druhá věc: srovnání pozice se dělalo **po** vstupech. Na grafu, kde vstupy procházely a exity
padaly, to znamenalo ratchet — každá seance přidala a nic neubralo. Deset se tak stalo
devatenácti. Srovnání jde teď první a dokud je účet nad knihou, nic nového se nenabízí.

| | v13 | v14 |
|---|---|---|
| **exity padají:** špička pozice | **46** | **6** |
| zrušených bracketů | 0 | 8 071 |
| zrušení na mrtvém příkazu | 0 | **0** |
| pracujících příkazů na konci | 10 144 | **2 164** |
| vstupů přijato | 9 821 | 9 885 |
| posunů stopu | 1 171 | 1 171 (beze změny) |
| špička pozice / strop | 60 / 60 | 49 / 60 |

Cestou jsem si v tom sám vyrobil deadlock: gate „počkej, dokud se pozice nezmění" se zablokoval
navždy ve chvíli, kdy call prodal dva a koupil dva a pozice zůstala stejná — order vrstva po
29 vstupech ztichla. Teď to není gate, ale korekce: nevyplněný prodej se jeden call počítá jako
vyplněný.

### P11 (nové, 30. 9.) — osiřelé pozice z předchozího běhu. HOTOVO

Tři běhy za sebou nechaly na grafu pozici, kterou další běh neumí uklidit: 10 → 19 → 27.
Mechanismus: reload presetů nebo restart Sierry přestaví knihu od nultého baru a **zahodí
všechna ID příkazů**, která si studie držela. Brackety po předchozím běhu se tím stanou
nedosažitelnými — dál pracují, jejich množství dál kryje pozici, a tržní prodej, který by ji
srovnal, se odmítne. Každý běh přidal to, co předchozí už nedokázal ubrat.

**Tohle se kódem zpětně spravit nedá** — ta ID jsou nenávratně pryč. Studie proto nově
odmítne obchodovat, dokud není účet vyrovnaný, a řekne to (jednou, ne každý call):

```
Multi-Swing: NOT TRADING. The account holds 27 contracts that this run did not place ...
```

Ve status boxu `NOT TRADING - flatten the account first` + řádek `FLATTEN`.

| start s 27 osiřelými kontrakty | v13 | v15 |
|---|---|---|
| vstupů přijato | 9 821 | **0** |
| co to řekne | nic | jednou `NOT TRADING` |

Se vyrovnaným účtem je chování bit-identické s v14 (9 885 vstupů, 8 071 zrušených bracketů,
1 171 posunů stopu, špička 49).

### P12 (nové, 30. 9.) — odprodej přebytku nemůže fungovat. NEDOŘEŠENO

Sierra to konečně řekla sama, v *Trade → Trade Activity Log*:

```
SellExit signal is ignored. ... there are already working exit orders that will flatten the
position. Current Position with working exit orders: 0. Current Position: 21.
```

`Position with working exit orders: 0` je celá odpověď. Každý držený kontrakt je už krytý
pracujícím stopem nebo targetem, takže nezůstalo nic nekrytého, co by další prodej mohl
legitimně zavřít. **Proto v celé session prošel každý BUY a neprošel ani jeden SELL** — nebyl to
špatně nastavený účet, ani zbytek z předchozího běhu, ani rychlost replaye. Byl to výstup, který
z principu nemůže existovat. Opakovat ho na jakékoli rychlosti a jakémkoli účtu nemělo šanci.

Tři moje předchozí diagnózy (menu Trade, zapomenuté brackety, osiřelé pozice) byly vedle. Každá
z nich opravila něco reálného, ale příčina to nebyla.

**Směr opravy je jistý:** výstup musí jít **skrz** bracket, ne okolo něj. Target presetu je
pracující sell limit nad trhem; posunutý pod trh se vyplní okamžitě a sundá právě ty kontrakty.
Preset bez targetu (signálový exit nenese cenu) má posunout stop. Sell limit pod trhem je vždy
platná cena, sell stop nad trhem není — proto limit, kde existuje.

**Implementace (hotovo 30. 9., verze `2026-09-30.16`).** Výstup jde teď skrz target: ten je
pracující sell limit nad trhem, posunutý pod trh se vyplní okamžitě a sundá právě kontrakty toho
presetu. Preset bez targetu (13 ze 48 má čistě signálový exit a žádnou cílovou cenu) má stop
zrušený — tím se jeho kontrakty odkryjí a tržní prodej pro ně Sierra přijme. Sell limit pod trhem
je vždy platná cena; sell stop nad trhem není, proto se stopy neposouvají přes trh.

Cestou se našly **tři místa, kde se záznam nohy zahodil, zatímco kontrakty byly pořád na účtu**:
při neúspěšném retire, při znovuvstupu téhož presetu ve stejné seanci (přepsal starou nohu), a ve
vstupní smyčce u presetu, který kniha právě zavřela. Kontrakty pak nepatřily nikomu: kniha je
nepočítala, žádný bracket se nedal řídit, a tržní prodej pro ně byl odmítnutý jako krytý. Trvale
zaseknuté, při každém běhu. Noha se teď zahodí, až když je prokazatelně pryč.

### Čím to ověřené NENÍ

Offline simulátor tenhle režim selhání **nereprodukuje**. Na jeho grafu je krytí totální a zůstane
totální, protože první prodej je odmítnut a tím se žádný bracket neuvolní. Ve stubu první prodej
projde a tím se to rozmotá — takže se stav, ve kterém jeho Sierra trvale je, ve stubu nikdy
nenastane. Během ladění jsem ve vlastním stubu našel tři chyby modelu (plnil i trailing stopy,
počítal krytí `covered/2`, nerušil brackety po prodeji) a každá měnila výsledné číslo víc než
změny ve studii. **Ladit proti tomu číslu dál by bylo ladění modelu, ne skriptu.**

Co ověřené je: rozhodovací jádro je bit-identické s `99543aa`, pojistka proti osiřelé pozici i
cut-off po pěti odmítnutích fungují, a v opraveném stubu proběhne celé období bez uváznutí
(9 332 vstupů, 689 výstupů přes bracket, žádný přeprodej).

**Verdikt dá až jeho replay.** Původní zápis: Stub teď vynucuje Sierřino skutečné pravidlo (prodej je odmítnut
pro kontrakty krytý pracujícím příkazem), takže se to dá poprvé měřit offline:

| varianta | vstupů | exitů přes bracket | prodejů odmítnutých jako krytých |
|---|---|---|---|
| `.15` (dnes v repu) | 46 | 3 | **15** |
| prototyp přes bracket | 46 | 19 | **12** |
| tentýž bez dvojího účtování | 41 | 14 | **15** |

Prototyp je lepší, ale pořád ne čistý, takže se necommituje ani neposílá. Zbývající odmítnutí
vznikají u nohou, k nimž se nedá dostat ID rodičovského příkazu — ty zůstanou kryté a zrušit se
nedají. Doladit to chce návrh, ne úpravu o jeden řádek.

### Co se pořád vyčíst nedá

Simulace dokazuje, že studie **nepožádá** o zrušení cizích stopů a že odprodej nikdy neprodá
víc, než se drží. Nedokazuje, co Sierra udělá sama od sebe. V *Trade → Trade Orders and
Positions* musí být otevřených stop příkazů právě tolik, kolik je otevřených presetů se
stopem. To platí jen pro Input 2 = Yes; v grafové simulaci to okno zůstává prázdné a počítat
se musí z grafu.

## P13 — tržní prodej, který nešel, a proč už nejde potřeba (hotovo, `.17`)

`.16` na jeho grafu poprvé prokazatelně odvedla exit přes bracket:

```
EXIT C<wvwapxsd_3 through its own bracket - target order 162534 moved to 7729.50 for 1 contract(s).
EXIT RSIx<x_1 - no target to steer, so its stop (order 162552) was cancelled ...
```

Takže `GetAttachedOrderIDsForParentOrder`, `ModifyOrder` i `CancelOrder` na jeho účtu fungují a
`parentOrderId` je platné — to je ta podmínka, kterou offline potvrdit nešlo. Zbytkový tržní
`SELL 2 from 29 to 27` se ale pořád vracel s `-1` a po pěti odmítnutích zamkl vrstvu.

Důvod byl v účtování, ne v Sieře. Noha se zahazovala ve chvíli, kdy exit **odešel**, ne když
dorazil. Fil nebyl potvrzený do dalšího volání, takže ty kontrakty v dalším volání nikdo nehlásil,
staly se z nich přebytek a šly na trh — kde je Sierra odmítla, protože posunutý target je pořád
krył. Pět takových a `ORDER PLACEMENT STOPPED`.

Co se změnilo:

1. **Noha přežije svůj exit.** Posunutý target/stop je pracující příkaz; studie si pamatuje jeho
   cenu, kontrakty se dál počítají jako držené, a když trh od té ceny odejde, příkaz se za ním
   posune. Noha se pustí teprve, když bracket nehlásí žádné živé dítě. Po osmi voláních bez filu
   se bracket zruší a kontrakty jdou na trh — to je jediná cesta, jak se dají ztratit z dohledu,
   a je to vidět v logu.
2. **Preset bez targetu se taky řídí bracketem.** Třináct presetů má jen stopku. Dřív se rušila a
   čekalo se na tržní prodej — což ty kontrakty mezitím nechávalo **nekryté**. Teď se stopka posune
   tick nad trh, kde se spustí okamžitě; když to routa odmítne, spadne se na zrušení jako dřív.
   V offline běhu to snížilo počet zrušených bracketů z 2 933 na 0.
3. **Tržní prodej prodává jen to, co nehlásí žádný preset.** Množství se nepočítá z rozdílu proti
   knize, ale jako *pozice mínus součet nohou*. Co drží nějaký preset, tam nikdy nejde, protože to
   je krytý a Sierra to odmítne. Odvozuje se to z nohou, ne z paměti na to, co se poslalo — jak fily
   dosedají, pozice klesá a to číslo klesá s ní, takže není co nechat vyexpirovat nebo rozejít.
4. **Znovuvstup čeká.** Jedna noha neunese dvě obchody, takže preset, který zavřel a hned otevírá,
   nedostane vstup, dokud staré kontrakty nejsou z účtu. Přepsání nohy bylo to, co z nich dělalo
   kontrakty bez vlastníka.

Změřeno na 4 680 seancích (ES, risk unit 1), se záměrným zdržením filu o daný počet volání studie:

| zdržení filu | vstupů `.16` | vstupů `.17` | odmítnuto jako kryté `.16` | `.17` | přeprodejů `.17` |
|---|---|---|---|---|---|
| 0 volání | 9 332 | 9 367 | 5 | **0** | **0** |
| 1 volání | 46 | 9 367 | 5 | **0** | **0** |
| 2 volání | 46 | 9 367 | 5 | **0** | **0** |
| 5 volání | 142 | 9 367 | 19 | **0** | **0** |
| 10 volání | 73 | 9 367 | 8 | **0** | 117 |

`.16` se složila při jakémkoli zdržení; `.17` je na zdržení nezávislá až k sedmi voláním. Rozhodovací
jádro je pořád bit-identické (feature dump i žurnál 10 206 řádků), pojistka proti osiřelé pozici i
cut-off fungují, dávkový a inkrementální běh se rovnají.

### Ve stubu se cestou našly další dvě chyby modelu

Obě posouvaly číslo víc než změny ve studii, takže stojí za zápis:

- **Fronta zdržených filů byla jedna hromada s jedním odpočtem.** Druhý prodej odpočet restartoval,
  takže graf, který prodává v každém volání, se nikdy neusadil a pozice dojela na strop bez ohledu
  na to, co studie dělá. Teď má každý prodej svůj vlastní odpočet.
- **Prodej rušil brackety živých obchodů.** Při vynuceném krytí může tržní prodej vzít jen
  nekryté kontrakty, takže žádný bracket rušit nemá — a rušením si stub sám bral záznam o živém
  obchodu: studie pak viděla prázdný bracket u presetu, který kontrakty pořád držel, pustila nohu,
  a z těch kontraktů se stal přebytek, který prodala. 3 216 kontraktů z offline prodejů byl stub,
  jak si žere vlastní stav.

### Co ověřené pořád není

Že Sierra přijme **stopku posunutou nad trh**. Stub ji plní, jeho routa ji přijmout nemusí. Když
ji odmítne, spadne to na zrušení stopky jako v `.16` a v logu bude
`could not steer <preset>'s stop (... Sierra returned -1)` — z toho se to pozná na první pohled a
ty kontrakty jsou pak chvíli nekryté, než je vezme tržní prodej. Zbytek `.17` na tom nestojí.

## P14 — vlastní simulace grafu neumí řídit brackety, a jedna noha uměla zaplavit log (hotovo, `.19`)

Jeho Message Log z `.17` rozhodl dvě věci, jednu o Sieře a jednu o mém kódu.

### Sierra: `ModifyOrder` v `Send Orders To Trade Service = No` neexistuje

S `Yes` (běh `.16`) projde `EXIT ... through its own bracket - target order 162534 moved to
7729.50`. S `No` přijde na tentýž příkaz `could not steer C<wvwapxsd_4's target (order 162689 to
3654.00, Sierra returned -1)` — a `CancelOrder` je odmítnutý taky, protože ten samý `targetId` se
vrací z `GetAttachedOrderIDsForParentOrder` i po zrušení. Vstupy se přijímají v obou režimech.

**Takže moje rada „pro replay dej Input 3 = No" byla špatná a platí obráceně: pro Full auto musí
být Yes.** `No` je plnohodnotné jen tam, kde se nic neposílá, tedy Signals only a Semi-auto.
Teorie, že replay do trade service nemůže fungovat kvůli cenám, se tím nepotvrdila — `.16` běžel
s `Yes` a brackety se řídit daly.

### Můj kód: noha, kterou nešlo zavřít, se zkoušela každé volání

`.17` u neúspěšného řízení nechala nohu žít, počítala ji jako drženou (správně) a **zkusila to
znovu v každém dalším volání studie** — se stejným logovacím řádkem. Při replayi na 30720X to je
tisíc identických řádek za sekundu, jeden a týž příkaz, celý běh. Nic se tím na účtu nezměnilo a
všechno ostatní v logu to pohřbilo.

Přidán stubový režim `STUB_ORDERS=sim_nomodify` (přijme vstupy s brackety, odmítne `ModifyOrder`
i `CancelOrder`), který ten stav reprodukuje. Na 468 barech:

| | řádek logu | z toho `could not steer` |
|---|---|---|
| `.17` | 8 779 | **6 970** |
| `.19` | 1 844 | **34** |

34 = jedna zpráva na nohu. Po `RETIRE_TRIES` pokusech se noha nechá být úplně: dál se počítá jako
držená (kniha zůstane poctivá), ohlásí se jednou `CANNOT CLOSE` s tím, co to nejčastěji znamená, a
víc se pro ni nezkouší nic. Objednávková vrstva jinak nezměněná a znovu přeměřená — žurnál
bit-identický, 9 367 vstupů, 0 odmítnutých jako krytých při zdržení filu 0, 1 i 5 volání.

---

## P15 — proč trade service odmítal každý vstup (vyřešeno, nastavení, nikoli kód)

Několik běhů `.17`–`.19` skončilo tak, že každý `sc.BuyEntry` vrátil `-1`, po pěti odmítnutích
sepnula pojistka a status box hlásil `STOPPED`. Kniha přitom držela svoje (`book 10`), účet
nedržel nic (`position 0`), takže nic z toho nebylo v objednávkové vrstvě — ven se prostě
nedostal ani první příkaz.

### Co to bylo

*Trade → Auto Trading Enabled for Chart* si **Sierra sama shazuje při startu chart replaye**
(a při reloadu grafu a změně symbolu). Zaškrtnutí před spuštěním replaye je tedy bez účinku.
Musí se zaškrtnout **až když replay běží**, a pak teprve zvednout západku přepnutím
Inputu 5 *Reload Presets*. Zapsáno do `NASTAVENI.md`, kapitola o zapnutí pro účet.

### Jak se to dalo poznat z logu, a proč to nešlo dřív

Rozhodující bylo, že u toho `-1` Sierra do Message Logu **nenapsala ani řádek** — v celém bloku
byly jen řádky s prefixem studie plus dva `Replay jump`. Sierra odmítá volání na vstupu, ještě
než z něj postaví příkaz; kdyby příkaz postavila a odmítla ho až pak (cena, zamítnutí účtem),
řádek o tom napíše. **Mlčící `-1` tedy znamená, že Sierra odmítla ještě před vznikem příkazu.**

**Opravuji, co tu stálo dřív:** tvrdil jsem, že to znamená „tuhle bránu nebo chybějící trade
account, a nic jiného". To bylo úzké. Před vznikem příkazu odmítá i **strop pozice**
(`sc.MaximumPositionAllowed`), viz P16 — a ten to nakonec byl podruhé.

Rychlý rozhodovací test, který tu příště zkrátí hledání: nechat replay běžet a poslat **ručně
z Trade Window** jeden market BUY s bracketem. Projde → brána je otevřená, hledej jinde.
Neprojde → je to nastavení.

### Co se tím zároveň vyvrátilo

Podezření, že na continuous back-adjusted grafu (`ESZ26_FUT_CME [CB]`, kde ES 2019 vychází na
3630 místo reálných ~2900) trade service odmítne stop a target spočítané z grafových cen, protože
reálný kontrakt je na jiné úrovni. **Neodmítne.** Po opravě brány přišel fill na `3818.25`, tedy
v cenách grafu — Sim plní z replayovaných dat, ne z živého trhu kontraktu. `[CB]` je pro full
auto replay v pořádku.

### Co zůstává na sledování

`book` a `position` se ve status boxu po rozjezdu na chvíli rozcházejí (viděno `book 5`,
`position 0`). Očekávané, dokud jde o latenci filu — příkazy odešly v tomhle volání a účet je
ještě nenahlásil. Rozcházet se **trvale** přes několik volání by znamenalo desync a patří to do
`P13`/`P14` mechaniky, ne sem.

---

## P16 — strop pozice byl šest kontraktů a nikde to nebylo vidět (`.20`)

Po opravě brány z P15 jeden příkaz prošel a naplnil se (`Trade: 1@3818.25`), takže auto trading,
účet i Trade Simulation Mode byly v pořádku. Následující dávka pěti vstupů přesto spadla na `-1`
a status box přepnul na `STOPPED`. Ceny přitom byly v pořádku: při closu ~3836 šly stopy
3717–3783 (pod trhem) a targety 3849–4093 (nad trhem), tedy na správných stranách.

### Co to je

`Max Gross Exposure` (Input 35 v dialogu, `IN_MAX_GROSS = 34`) se počítá **v MES ekvivalentech**
a na `sc.MaximumPositionAllowed` se dělí multiplikátorem instrumentu:

```cpp
const double mult = sc.Input[IN_INSTRUMENT].GetIndex() == 1 ? 10.0 : 1.0;
sc.MaximumPositionAllowed = (int)std::max(1.0, std::floor(grossInput / mult));
```

Výchozích **60 MES** tedy na **ES** dává strop **6 kontraktů**. To je nejtvrdší limit v celém
skriptu a byl jediný, který nikam nepsal svou hodnotu. Kniha se v něm přitom pohybuje přesně na
hraně (`open 5`, `book 5`), takže každá další dávka vstupů do něj naráží.

Vlastní pojistka skriptu to nezachytí: projektuje si dopředu jen **čistou pozici na účtu**
(`projected = account`), zatímco Sierra ke stropu připočítává i **pracující děti bracketů**.
Pět vstupů s bracketem je pro Sierru 5 parentů + 5 stopů + 5 targetů; proti stropu 6 to nemá
šanci projít. Oba stropy si tedy nepočítají totéž.

### Co je v `.20` opravené

Nic v logice — jen se ten strop **jednou při loadu vypíše**, s hodnotou, s inputem, ze kterého
vznikl, a s použitým multiplikátorem. Stálo to hodinu hledání ve špatném místě právě proto, že
`-1` nenese důvod a nenesl ho ani tenhle limit.

### Co ověřené NENÍ

Přesné pravidlo, podle kterého Sierra ke `MaximumPositionAllowed` počítá pracující příkazy.
Že tam brackety připočítává, je nejlepší vysvětlení pozorovaného (odmítnutí všech pěti vstupů
při stropu 6 a téměř ploché pozici), ale z dokumentace to potvrzené nemám. Kdyby se ukázalo,
že Sierra počítá jen parenty, zbývá vysvětlit odmítnutí prvního vstupu z ploché pozice —
1 ≤ 6 projít mělo.

### Co s tím dál

Pro test 48 presetů na ES při risk unit 1 je potřeba strop řádu 48 kontraktů, tedy
`Max Gross Exposure` okolo **480–600** MES ekvivalentů. Až bude potvrzeno, že to byl on,
patří sem rozhodnutí, jestli:

- zvýšit výchozí hodnotu (60 MES je rozumné pro MES, ale na ES je to 6 kontraktů), nebo
- nechat projekci skriptu počítat i pracující děti bracketů, aby si oba stropy odpovídaly, nebo
- oboje.

---

## P17 — proč Sierra odmítala KAŽDÝ příkaz: trading flagy byly nastavené na špatném místě (`.21`)

Tohle byla po celou dobu chyba v mém kódu, ne v nastavení Sierry. Prošel jsem P15 (brána) i P16
(strop pozice) a ani jedno to nebylo — uživatel potvrdil, že `Auto Trading Enabled - Global`,
`Auto Trading Enabled for Chart` i `Trade Simulation Mode` jsou **všechny zatržené**, strop byl
po opravě 60 kontraktů proti poptávce 7, účet byl `Flat`, ceny na správných stranách trhu.

### Co to bylo

Šest ACSIL proměnných není runtime stav, ale **konfigurace studie**. Sierra je čte, když se studie
konfiguruje, tedy v bloku `if (sc.SetDefaults)`. Já je nastavoval **až v normálním průchodu**,
za `return` toho bloku:

```cpp
if (sc.SetDefaults) {
    ...
    return;            // ← Sierra čte konfiguraci sem
}
...
sc.SupportAttachedOrdersForTrading = 1;   // ← a já ji nastavoval až tady
```

Zůstávaly tedy na Sierřiných vlastních defaultech. A `sc.SupportAttachedOrdersForTrading` má
default **false**. Každý vstup přitom nese `Stop1Price` a `Target1Price`, takže to byl příkaz,
který Sierra přijmout nemůže — a odmítla ho generickým `-1` bez důvodu.

### Proč to sedí na všechno, co jsme viděli

| pozorování | vysvětlení |
|---|---|
| odmítnuto **každé** `BuyEntry`, vždy, i z ploché pozice | bracket je nepřijatelný bez ohledu na stav |
| `-1` bez jediného řádku od Sierry | odmítnutí při validaci, příkaz nikdy nevznikl |
| ruční příkaz z Trade Window **projde** | ruční příkazy na tomhle flagu studie nezávisí |
| v grafové simulaci (`Send = No`) byly vstupy **přijímány** | vnitřní simulace grafu je permisivnější |
| nikde v logu ani jeden `Multi-Swing: BUY ...` | tak to taky bylo: neprošlo nic |

Ten poslední řádek byl klíč a ležel ve všech logách od začátku. Skript loguje každý **přijatý**
příkaz a ani jeden takový řádek neexistoval — zatímco `SIGNAL` a `EXIT` řádky ano, takže log level
na INFO byl. Měl jsem to číst dřív a místo toho jsem dvakrát hledal v nastavení Sierry.

### Oprava

Těch šest se nastavuje v `SetDefaults`, kde je Sierra čte. Přiřazení v normálním průchodu zůstala
jak byla, aby build, který je případně čte per-call, viděl stejné hodnoty:

```cpp
sc.AllowMultipleEntriesInSameDirection  = 1;
sc.SupportReversals                     = 0;
sc.AllowOnlyOneTradePerBar              = 0;
sc.SupportAttachedOrdersForTrading      = 1;
sc.AllowEntryWithWorkingOrders          = 1;
sc.CancelAllOrdersOnEntriesAndReversals = 0;
```

`sc.SendOrdersToTradeService` a `sc.MaximumPositionAllowed` zůstávají v runtime — ty se mají
měnit s Inputy.

### Co ověřené NENÍ

Že to byl **právě** `SupportAttachedOrdersForTrading` a ne jiný z té šestice. Všech šest se
opravilo jedním zásahem a rozlišit je bez živé Sierry nejde. Nejlepší kandidát je on, protože
jediný z nich gatuje attached ordery, a každý odmítnutý příkaz nějaký bracket nesl.

---

## P18 — pojistka proti nechtěnému live (`.21`)

`Send Orders To Trade Service = Yes` znamená jen „posílej". Jestli to jde do `Sim1` nebo na ostrý
účet, rozhoduje `Trade → Trade Simulation Mode`, což studie **nevidí a nenastaví**. Status box
proto čte `FULL AUTO - ORDERS LIVE` úplně stejně pro replay i pro reálné peníze, a při 48
presetech posílajících market ordery je to ta nejnebezpečnější vlastnost celého setupu.

Nový Input 89 `LIVE TRADING CONFIRMED (seatbelt)`, default **No**. Dokud není Yes, Full auto
spočítá a zaloguje celou knihu, ale **nepošle nic**, a status box hlásí
`FULL AUTO - ARMED, not sending: Live Trading Confirmed = No`. Červená barva boxu se váže na to,
co opravdu může odejít, ne jen na režim.

Je to pás, ne zámek: studie Sim od live rozlišit neumí, takže to jen vynucuje vědomé rozhodnutí.

Měřeno na 2400 barech, 48 presetech:

| `LIVE_CONFIRM` | přijatých BUY | odmítnutí | hlášení | řádků žurnálu |
|---|---|---|---|---|
| 0 | **0** | 0 | 1× | 236 |
| 1 | **218** | 0 | 0 | 236 |

Žurnál **bit-identický** v obou případech — pojistka se nedotýká rozhodovacího enginu. Do stubu
přidán override `LIVE_CONFIRM=0|1`, aby se dala měřit i zavřená větev; harness si ji jinak drží
otevřenou, jinak by každý test objednávkové cesty měřil prázdný běh.

---

## P19 — `sc.MaximumPositionAllowed` byl NULA (`.22`)

Status box z `.21` vypsal na jeho grafu:

```
cap       0 ES contracts   (Max Gross 600 MES)
```

**Nula.** Při `Max Gross Exposure = 600` a instrumentu ES má být 60. Runtime přiřazení tedy
neprošlo — `sc.MaximumPositionAllowed` je, stejně jako ta šestice z P17, **konfigurace studie**,
ne runtime stav. Sierra držela nulu a nulový strop odmítá každý jediný vstup.

To je ta příčina, kterou jsme hledali od P15. Všechno ostatní byly následky:

- P15 (brána) — brána byla v pořádku, hledal jsem špatně
- P16 (strop 6) — strop byl 6, ale ani 60 by nepomohlo, protože Sierra držela 0
- P17 (attached orders) — reálná chyba, opravená, díky ní se `-1` změnilo na `-8995`

A ukázal to **ten jediný řádek, který jsem v `.20` přidal proto, aby ten strop byl vidět.**
Bez něj bychom hádali dál.

### Oprava

Sierřin strop se nastavuje v `SetDefaults` na **1000** a runtime ho už jen zvyšuje, nikdy nesnižuje.
Skutečný limit je `Max Gross Exposure`, který vynucuje studie sama v `CapsAllow` a v projekci
v `SyncOrders` — v MES ekvivalentech, tedy v jednotce, ve které je kniha napsaná. Sierřin strop je
od teď jen záchrana proti utržení, ne pracovní limit, a ty dva se nemůžou rozejít v jednotkách.

Status box ukazuje obojí, aby se nula už nikdy neschovala:

```
cap       60 ES book / 1000 Sierra   (Max Gross 600 MES)
```

### `-8995` a skip kódy

Kódy v pásmu −8990…−8999 jsou Sierřiny **skip** kódy, ne odmítnutí: nic neodešlo a účtu se nikdo
nedotkl. Hláška `STOPPED` přitom radila „zavři pozici ručně" — pozici, která nikdy nevznikla.
Opraveno: skip má vlastní hlášení i vlastní text ve status boxu, a hint říká, jak si význam kódu
najít v `scconstants.h` na stroji, kde Sierra běží.

### Co ověřené NENÍ

Co přesně `-8995` znamená. Je to skip kód, ne odmítnutí, ale jeho jméno je v Sierřině hlavičce na
jeho disku, ne tady. Dost možná je to právě „position limit" a zmizí s touhle opravou.

### Nový nález k dořešení

V harnessu jde **83 vstupů** ven s `stop 0.00 target 0.00` — tedy bez stopu i targetu. Ve full
auto to je nekrytá pozice. Pro limitní presety (`LMT_*`) to může být správně, pro ostatní ne.
Patří to k rozhodnutí, jestli ve full auto odmítnout vstup bez stopu rovnou ve studii.

---

## P20 — objednávková cesta prokázána, a dvě moje diagnózy odvolány (`.23`)

Jeho log z `.22` obsahuje to, na co jsme čekali od P15:

```
Multi-Swing: BUY 1 C<dvwapxsd_1  stop 3646.50  target 3819.00
Multi-Swing: BUY 1 C<dvwapxsd_3  stop 3639.25  target 3926.25
Multi-Swing: BUY 1 C<wvwapxsd_2  stop 3589.00  target 4163.25
Multi-Swing: BUY 1 IBS<x_1       stop 3703.00  target 3798.75
Multi-Swing: STOP MOVED for IBS<x_1 from 3703.00 to 3735.00 (order 162856)
```

Čtyři přijaté vstupy s brackety a jeden úspěšně posunutý stop. Žádné `-1`, žádné `-8995`,
žádné `STOPPED`. **Jediná skutečná příčina byla P17** — `sc.SupportAttachedOrdersForTrading`
nastavovaný mimo `SetDefaults`.

### Odvolávám P19: strop nikdy nebyl nula

`sc.MaximumPositionAllowed` **čte zpátky vždy 0**, bez ohledu na to, co se do něj zapsalo. Je
z pohledu studie write-only. Ten „cap 0", na kterém jsem postavil celé P19, byl artefakt čtení,
ne skutečný strop — a v tom samém logu, kde se čte 0, příkazy procházejí.

Co z `.22` zůstává platné: nastavit ho v `SetDefaults` a nechat skutečný limit na vlastním
`Max Gross Exposure`. Co bylo špatně: tvrzení, že nula blokovala vstupy, a hláška
„if Sierra's backstop ever reads 0 here ... that is a study bug", která uživatele zbytečně
strašila. Obojí odstraněno, ze status boxu i z logu.

### Odvolávám P14: grafová simulace brackety řídit UMÍ

Tvrdil jsem, že vlastní simulace grafu odmítá `ModifyOrder` a `CancelOrder`, a napsal na to
varování. `STOP MOVED ... (order 162856)` v chart simulaci to vyvrací. Příčina byla znovu táž:
bez `SupportAttachedOrdersForTrading` neexistovaly žádné děti bracketu, které by šlo modifikovat,
a Sierra vracela `-1` na modifikaci neexistujícího příkazu.

Praktický důsledek: **`Send Orders To Trade Service = No` je pro replay plnohodnotný režim.**
Fily jsou deterministické z barů grafu, brackety se řídí, účtu se nikdo nedotkne a není co špatně
nastavit. To varování je z kódu odstraněné.

### Log hygiena

Hláška o režimu se říkala jednou per **full recalculation**. Replay rekalkuluje pořád a každý
reload presetů je další, takže se v třiceti sekundách jeho logu objevila čtyřikrát. Teď je jednou
per **load** — režim se nemění mezi rekalkulacemi, mění se se změnou Inputu, a ta reload vyvolá.

### Měřeno

| `LIVE_CONFIRM` | přijatých BUY | odmítnutí | řádků žurnálu | hláška o režimu |
|---|---|---|---|---|
| 0 | 0 | 0 | 236 | 1× |
| 1 | 218 | 0 | 236 | 1× |

Žurnál bit-identický s `.22`. Žádná zmínka o „backstop" v logu.

### Zbývá

- `NOT TRADING. The account holds 4 contracts that this run did not place` — sirotčí hlídka
  zafungovala správně, když během otevřených pozic přeladil presety. Chování je v pořádku, postup
  je v hlášce.
- 83 vstupů v harnessu jde ven bez stopu i targetu (`stop 0.00 target 0.00`). Dotaz na uživatele
  je odeslaný, odpověď zatím není.
- Parita 2008–2026 v Semi-auto proti offline harnessu. Teprve teď má smysl.

---

## P21 — `NOT TRADING` na knize, která byla v pořádku (`.24`)

Status box hlásil:

```
book      3 contracts   position 3
FLATTEN   the account holds contracts this run did not place
```

`book 3` a `position 3` **se shodují**. Účet drží přesně to, co kniha říká. Sirotčí pojistka
přesto latchla `NOT TRADING` a žádala ruční flatten.

### Proč

Podmínka je `send && S.ordersPlaced == 0 && account > 0`. A `ordersPlaced` i `legs` se nulovaly
při **každé plné rekalkulaci**:

```cpp
if (start == 0) { ...
                  S->legs.clear();
                  S->ordersPlaced = 0; ... }
```

Replay rekalkuluje při každé změně Inputu. Takže jakmile měl otevřenou pozici a na čemkoli hnul,
`ordersPlaced` spadlo na 0, pojistka uviděla kontrakty, o kterých si myslela, že je tenhle běh
neposlal, a zamkla obchodování — kvůli stavu, který nikdy nebyl rozbitý. Přesně to, co mu bránilo
rychle testovat.

### Oprava

Rekalkulace **nezahazuje** `legs` ani `ordersPlaced`. Přehrává tytéž bary a staví tytéž stavy
presetů, ale příkazy, které ty nohy popisují, jsou živé na účtu a nikam se neděly. Indexy presetů
se rekalkulací nemění, takže noha `k` dál popisuje preset `k`.

Reload presetů si handly nechá taky — ale **jen když je seznam presetů stejný**. Id se odeberou
před načtením a porovnají po něm. Stejný seznam = každý handle pořád ukazuje na obchod, pro který
vznikl. Jiný seznam = indexy už neznamenají totéž a handly jsou skutečně bezcenné, takže jdou
pryč a pojistka zafunguje.

### Měřeno

| scénář | `NOT TRADING` | přijatých BUY |
|---|---|---|
| běžný běh, `CHUNK=6` | **0** | 218 |
| běžný běh, `CHUNK=1` (víc rekalkulací) | **0** | 224 |
| `STUB_START_POS=5` — účet drží cizí kontrakty | **1** | **0** |

Poslední řádek je ten důležitý: pojistka se nevypnula, jen přestala hlásit planý poplach.
Když účet opravdu drží kontrakty, pro které studie nemá handly, pořád odmítne poslat cokoli.
Žurnál bit-identický s `.23`.
