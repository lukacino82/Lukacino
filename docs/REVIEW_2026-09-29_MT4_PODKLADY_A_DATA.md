# Review: použitelnost nahraných MT4 podkladů pro alpha systém

Datum: 29. 9. 2026
Předmět: čtyři nahrané soubory (3× `.ex4` indikátor, 1× ZIP s EA a návodem) + inventura toho, co už v repozitáři leží.
Otázka: dá se z toho něco použít pro stavbu alpha systému?

**Krátká odpověď: z nahraných souborů prakticky nic jako kód. Jeden z nich je ale užitečný jako specifikace rizikového modulu, který v blueprintu dosud chybí. Nejcennější věc pro alpha systém přitom v repozitáři už leží a je nerozbalená — 18 let minutových ES dat s order flow.**

---

## 1. Verdikt po jednotlivých nahraných souborech

### 1.1 `09_Leverage_levels.ex4`, `BCL_big_cycle_lines.ex4`, `rebel_ciary_posuvne.ex4`

| Položka | Zjištění |
|---|---|
| Autor | Copyright 2015, Domogled s.r.o., https://www.domogled.com |
| Verze | 1.00 |
| Formát | MT4 EX4, build 600+ — tělo programu je šifrované |
| Velikost | 28,6 kB / 30,0 kB / 12,2 kB |
| Čitelné řetězce | pouze copyright, URL, verze |
| Názvy Inputs | **žádné** — nelze vyčíst |
| Logika | **nelze vyčíst** |

Provedl jsem extrakci řetězců v ASCII i UTF-16. Kromě hlavičky nevychází nic — ani jména vstupních parametrů, ani popisky bufferů, ani názvy objektů. Dekompilaci nedělám: jde o komerční chráněný build třetí strany.

**Praktické důsledky:**

1. **Špatná platforma.** Jsou to MT4 indikátory. Alpha systém míří na Sierra Chart / ACSIL nad ES futures (viz `CORRECTION_ALPHA_BLUEPRINT.md`, sekce Sierra Settings). Ani po dekompilaci by se kód nedal přenést.
2. **Neověřitelné.** Blueprint má tvrdou vyřazovací podmínku: strategie nesmí používat data, která v okamžiku rozhodnutí nebyla známá. U zavřeného binárního indikátoru nelze ověřit, jestli nerepaintuje. Většina indikátorů typu "čáry/úrovně" repaintuje nebo kotví na zpětně známý extrém — přesně to, co blueprint zakazuje (D03: "Zakázat anchor vybraný až po znalosti budoucího dna").
3. **Koncepčně už pokryto.** Podle názvů jde o kreslení úrovní — tedy vrstva `Location`. Tu blueprint řeší skupinami D (VWAP kotvy) a E (VAL/VAH/POC) podstatně přísněji a s kauzálně definovanými kotvami.

**Použitelné jen takto:** pokud popíšeš slovně pravidlo, podle kterého se ty úrovně počítají (co je "big cycle line", z čeho se odvozuje "leverage level", jak se posouvají "rebel čáry"), dá se to přeimplementovat a otestovat jako `Location` filtr nad existujícími signály skupiny A/C. Bez toho popisu to je slepá ulička.

### 1.2 `EA-manazment-2-153694.zip` → `prikupovanie.ex4` + `prikupovanie.docx`

| Položka | Zjištění |
|---|---|
| Autor | Copyright 2016, Ondřej Flek (FLEK TRADING s.r.o.), flektrading.cz |
| Verze | 1.01 |
| Typ | MT4 Expert Advisor (ne indikátor) |
| Dokumentace | ano — `.docx` popisuje kompletní sadu Inputs |

Návod logiku popisuje jednoznačně. Jde o **averaging / grid EA řízený úrovní marže**:

- otevřeš libovolný obchod (stačí 0,01),
- EA dokupuje pokaždé, když margin level klesne na zadané %,
- až do `Max prikupu` (návod doporučuje strop brokera, standardně **200 obchodů**),
- zavírá se buď na TP/SL v ceně, nebo na TP/SL v měně účtu,
- druhá margin úroveň simuluje stopout.

**Jako obchodní strategii to nepoužívej.** Je to přímý rozpor s blueprintem:

- G04 explicitně říká: *"Každá další tranche musí mít samostatný risk budget; celkový stop a max gross limit jsou pevné. Nejde o martingale podle ztráty."* Tohle je přesně martingale podle ztráty.
- Velikost pozice mechanicky roste do neomezeného propadu — B01 to zakazuje.
- Neprojde vyřazovací podmínkou "zisk pochází z jediné epizody" naruby: takový systém generuje dlouhou řadu malých zisků a jednu totální ztrátu. Průměr vypadá skvěle až do dne, kdy účet skončí na nule.
- Cíl je porážet B&H na S&P 500. Averaging do ztráty nezvyšuje edge, jen mění tvar distribuce — přesouvá riziko do ocasu.

**Kde to naopak hodnotu má:** ten `.docx` je použitelná **specifikace rizikového modulu**, který v blueprintu chybí. `Lukacino_GlobalController` má v blueprintu jen zmínku "portfolio, order management, risk", žádné konkrétní vstupy. Inputs z tohoto EA se dají převzít **s obrácenou polaritou** — ne jako spouštěč dokupování, ale jako de-risking:

| Input z EA (dokupování) | Převrácený ekvivalent pro GlobalController |
|---|---|
| Margin level pre prikup | margin level, pod kterým se **zakáže nová expozice** |
| Margin level pre zatvorenie | margin level, na kterém se **povinně snižuje pozice** (tvrdý stopout před brokerem) |
| Max prikupu | `max gross contracts` napříč všemi rolemi |
| TP profit / SL profit (v měně účtu) | **portfolio-level equity stop** a denní profit target — nezávisle na per-trade stopech |
| Volume | základní risk unit, ze kterého role odvozují váhy |
| "najprv musíte vypnúť AOS" | manual-override interlock: ruční zásah musí nejdřív odstavit automat, jinak si systém pozici obnoví |

Ten poslední bod je reálná provozní lekce, ne teorie. Stojí za to ji do controlleru zapsat natvrdo.

---

## 2. Co už v repozitáři je — a je to řádově cennější

Inventura ukázala, že podklady pro alpha systém jsou rozpracované mnohem dál, než nahrané MT4 soubory naznačují.

### 2.1 Data

| Soubor | Obsah | Stav |
|---|---|---|
| `ES2008.zip` + `.z01`–`.z04` | **6 439 576 minutových barů, 2008-05-04 → 2026-09-25**, s `BidVolume`/`AskVolume` | **nerozbalené**, ale kompletní — ověřeno |
| `ES3000.zip` + `.z01`–`.z02` | 1min, 2018-07-08 → 2026-09, s order flow (220 MB) | nerozbalené; toto je zdroj pro dosavadní Phase 4 |
| `ES2008.txt` (v repu) | hodinové bary 2008 → 2026, **neupravená cena** | rozbalené |
| `es mini data new 2 (2).zip` | XLSX, 49 MB | nerozbalené |

Rozbalení split archivu: části se musí nejdřív sesypat (`cat ES2008.z01 ES2008.z02 ES2008.z03 ES2008.z04 ES2008.zip > spojeny.zip`), teprve pak rozbalit. Otestováno, soubor projde kontrolou integrity.

**Order flow (delta) je v minutových datech dostupný od 2010-12-27.** Do té doby jsou `BidVolume`/`AskVolume` nulové. To znamená ~15,8 roku delty, ne 18 — všechny strategie skupiny F je potřeba hodnotit až od 2011.

### 2.2 Výzkum

| Dokument | Obsah |
|---|---|
| `CORRECTION_ALPHA_BLUEPRINT.md` | 58 hypotéz ve skupinách A–G, čtyřvrstvá konstrukce Weakness → Location → Exhaustion → Trigger, entry/exit engine, portfolio rolí, vyřazovací podmínky, rozpočet Sierra Inputs |
| `REPORT.html` | S01–S25 **už odbacktestováno** na ES2008 jednotným profilem X2, včetně bety, alpha_t a bootstrapu proti B&H |
| `codex_astra_strategy_spec.json` | Phase 4 audited: 17 strategií s rozpadem discovery / validation / OOS, execution contract, production gates |
| `alpha_map.csv` | 334 řádků: MFE/MAE a win rate po horizontech 15m–EOD, rozděleno na DISC/VAL období |
| `tpsl_grid_5m.csv` | 1 701 kombinací TP/SL se čtyřmi časovými řezy včetně OOS 2025–2026 |

**Nic z nahraných MT4 souborů není v těchto materiálech nikde zmíněno** — ověřeno fulltextem. Jsou to cizí podklady mimo dosavadní linii výzkumu.

---

## 3. Tvrdý nález z už hotových testů

V `REPORT.html` je sloupec `bootstrap_beats_bh` — pravděpodobnost, že modul porazí buy & hold. Zadání přitom znělo, že strategie bez porážení B&H nemají smysl.

| ID | Strategie | Trades | PF | alpha_t | bootstrap_beats_bh |
|---|---|---:|---:|---:|---:|
| S01 | IBS Reversion | 388 | 1,54 | 2,39 | **0,266** |
| S12 | Turn of Month | 367 | 1,44 | 1,79 | 0,090 |
| S22 | IBS and Weekly VWAP | 246 | 1,60 | 2,32 | 0,062 |
| S05 | Donchian Close Extreme | 446 | 1,22 | 0,29 | 0,059 |
| S14 | MA100 Reclaim | 87 | 1,98 | 1,95 | 0,021 |
| S20 | Delta Exhaustion | 199 | 0,90 | −1,35 | 0,001 |

**Ani jeden z 23 proveditelných modulů nemá reálnou šanci porazit B&H.** Nejlepší je 26,6 %.

Zároveň ale S01 a S22 mají `alpha_t` přes 2,3 při betě 0,13–0,29. To není protimluv, je to přesná diagnóza: **tyto systémy mají statisticky kladnou alfu, ale prohrávají s B&H, protože jsou drtivou většinu času v hotovosti.** Blueprint má vyřazovací podmínku "poráží B&H pouze díky vyšší expozici". Tady platí zrcadlový problém — prohrávají kvůli nižší expozici.

Z toho plyne jediný logický závěr: **samostatný timing systém tuhle úlohu nevyřeší. Vyřeší ji G05 — Core Long + Tactical Correction Overlay.** Core drží expozici (a tím beta výnos indexu), overlay přidává právě tu alfu, kterou S01/S22 prokazatelně mají. G05 je v blueprintu popsaný, ale zatím **neotestovaný**, a je to jediná položka katalogu, která na zadanou otázku odpovídá.

---

## 4. Nález, který je potřeba opravit před rozšířením na 2008

Porovnal jsem cenové řady:

| Datum | `ES2008.txt` v repu (hodinový) | minutový `ES2008.txt` ze ZIPu | `ES3000.txt` |
|---|---:|---:|---:|
| 2008/5/5 | 1 407,25 | 2 045,00 | — |
| 2015/6/1 | 2 116,75 | 2 893,25 | — |
| 2020/3/16 | 2 445,00 | 3 270,50 | 2 450,75 |
| 2026/6/5 | 7 433,25 | 7 601,75 | 7 471,50 |

Minutová řada z `ES2008.zip` je **aditivně zpětně upravená** (back-adjusted) o roll — offset +638 bodů v roce 2008, +168 na konci. Hodinový soubor v repu je neupravený. `ES3000` je upravený jen mírně (+38 bodů), protože pokrývá kratší období.

**Proč to vadí:** blueprint stojí z velké části na procentních veličinách — `Drawdown(N)`, `CumRet(k)`, celý drawdown ladder B01 (−2 % … −20 %), ATH drawdown buckets v `codex_astra_strategy_spec.json`. Na aditivně upravené řadě jsou všechny tyhle prahy zkreslené. Propad o 10 % v roce 2008 se na upravené řadě (2 045 místo 1 407) spočítá zhruba o 45 % menší, než ve skutečnosti byl. Čím starší data, tím větší chyba — a právě ta stará data jsou důvod, proč 2008 vůbec rozbalovat.

**Řešení:** buď použít proporcionální (ratio) back-adjustment místo aditivního, nebo počítat procentní featury nad neupravenou řadou a P&L nad upravenou. Neupravenou cenovou hladinu poskytne hodinový soubor, který v repu už je.

Na `ES3000` (2018+) je zkreslení malé, takže dosavadní Phase 4 výsledky tím nejsou zásadně zasaženy. Rozšíření zpět na 2008 by tím ale zasaženo bylo.

---

## 5. Doporučený postup

Seřazeno podle poměru přínos / námaha.

1. **Rozbalit `ES2008.zip` a zařadit ho jako primární výzkumný dataset.** Rozšíří pokrytí z 8 let (2018+) na 18,4 roku a přidá 2008 GFC, 2010 flash crash, 2011 a 2015 — přesně ty krizové režimy, o kterých blueprint sám píše, že jich je v datech málo.
2. **Před tím vyřešit back-adjustment** podle bodu 4. Jinak bude celá skupina B na starých datech počítat nesmysly.
3. **Otestovat G05 (Core + Overlay).** Metrika je daná blueprintem: `Core + Overlay − Core` při stejném kapitálu, nákladech a risk limitu. Jako overlay nasadit S01 a S22 — jediné dva moduly s `alpha_t` nad 2. Tohle je podle mě jediná cesta, jak splnit podmínku "porazit B&H".
4. **Doplnit `Lukacino_GlobalController`** o rizikové vstupy podle tabulky v bodě 1.2 — margin thresholdy jako de-risking, portfolio equity stop, max gross cap, manual-override interlock.
5. **MT4 indikátory nechat stranou.** Pokud je chceš využít, pošli slovní popis pravidel; pak se dají přeimplementovat jako `Location` filtr a otestovat. Bez popisu s nimi nic nenaděláme.
6. **`prikupovanie` nenasazovat.** Ani na demu jako součást alpha systému — logika je v přímém rozporu s G04 a B01.

---

## 6. Co tento dokument netvrdí

Neříká, že S01, S22 nebo G05 mají alfu do budoucna. Dosavadní čísla pocházejí z období, které bylo opakovaně prohlíženo, takže to není čistý holdout. Production gates z `codex_astra_strategy_spec.json` — purged walk-forward, korekce na vícenásobné testování, block-bootstrap, stres nákladů, roll audit, paper execution — zatím neproběhly. Do jejich splnění jde o kandidáty, ne o systémy.
