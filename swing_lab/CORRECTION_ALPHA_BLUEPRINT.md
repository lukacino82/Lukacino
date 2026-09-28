# ES Correction Alpha Blueprint

Datum: 28. 9. 2026. Cíl: navrhnout multi-swing systém, který systematicky vyhledává slabost, korekce a vyčerpání prodejního tlaku v ES/S&P 500. Dokument je katalog testovatelných hypotéz. Není důkazem, že některá strategie má alfu nebo že budoucí výnos je zaručen.

## Ústřední konstrukce

Korekce není jediný signál. Je to stavový proces:

```text
0 Normal / trend
    ↓ narušení
1 Weakness: série ztrát, drawdown, vzdálenost od rovnováhy
    ↓ pokračující tlak
2 Impulse: vysoký range/ATR, gap, objem a negativní delta
    ↓ cena přestává reagovat na další prodej
3 Exhaustion / absorption
    ↓ reclaim úrovně nebo price confirmation
4 Entry armed
    ↓ target / time exit / invalidace
5 Recovery nebo failed correction
```

Každá strategie musí přesně určit čtyři vrstvy:

1. `Weakness`: co se na ceně pokazilo.
2. `Location`: kde se korekce odehrává vůči trendu, VWAP, value area nebo minulému drawdownu.
3. `Exhaustion`: zda tlak zrychluje, nebo ztrácí cenový účinek.
4. `Trigger`: co potvrzuje vstup bez použití budoucích dat.

Tím oddělíme „trh je přeprodaný“ od „přeprodaný trh pravděpodobně začal opravovat korekci“.

## Společné veličiny

Všechny hodnoty se počítají pouze z dokončených barů/session.

| Veličina | Definice |
|---|---|
| `RunDown` | počet po sobě jdoucích `Close[t] < Close[t-1]` |
| `CumRet(k)` | `Close[t]/Close[t-k]-1` |
| `Drawdown(N)` | `Close[t]/max(Close[t-N+1:t])-1` |
| `ATRShock` | `-Return[t] / (ATR[t-1]/Close[t-1])` |
| `DownRangeEffort` | `(Open-Close)/(High-Low)` na down baru |
| `CloseLocation` | `(Close-Low)/(High-Low)`; denní IBS |
| `DistanceMA` | `(Close-MA(n))/ATR` |
| `DistanceVWAP` | `(Close-VWAP_anchor)/VWAP_SD_anchor` |
| `DeltaZ(n)` | `(Delta-rolling_mean)/rolling_sd` |
| `CVD(k)` | součet delty posledních k dokončených intervalů |
| `PriceResponse` | cenový pokles v ticks / agresivní sell volume; malá absolutní reakce při silném prodeji značí možnou absorpci |
| `RecoveryFraction` | `(Close-current correction low)/(correction high-correction low)` |
| `TimeFromPeak` | počet session od posledního Ndenního maxima |
| `TimeFromLow` | počet session od aktuálního minima korekce |

VAP veličiny (`VAL`, `VAH`, `POC`) se počítají z price-level volume v Sierra Chart. Nelze je rekonstruovat přesně z minutového OHLCV.

## A. Série ztrátových dnů a čistá cenová slabost

### A01 Consecutive Down Closes

- Weakness: 2, 3, 4 nebo 5 nižších close.
- Location: samostatně testovat nad rostoucí MA200, bez filtru a pod MA200.
- Trigger: následující RTH open nebo první close nad předchozím high.
- Invalidace: další close pod korekčním low nebo ATR stop.
- Hypotéza: nucené krátkodobé prodávání se vyčerpá rychleji v dlouhodobém bull režimu.

### A02 Weighted Losing Streak

- Nejen počet dnů: skóre `sum(sign(return) × |return|/ATR)` za 3–7 session.
- Série malých ztrát se odliší od jednoho velkého šoku.
- Vstup až při zpomalení posledního normalizovaného poklesu.

### A03 Cumulative K-Day Decline

- `CumRet(2/3/5/10)` pod historickým percentilem 1/5/10 %.
- Prah se stanoví rolling pouze z minulosti, ne z celé historie.
- Varianty: okamžitý vstup, reclaim poloviny posledního down baru, reclaim SMA3.

### A04 ATR-Normalized Shock

- Jednodenní nebo dvoudenní pokles o 1/1,5/2/3 předchozího ATR.
- Rozdělit gap component a RTH component.
- Hypotéza: stejný procentní pokles má jiný význam v klidném a volatilním režimu.

### A05 Accelerating Selloff

- Tři záporné výnosy, každý absolutně větší než předchozí.
- Vstup se nespustí během akcelerace; čeká na první den, kdy pokles zůstane záporný, ale jeho velikost klesne.
- Testuje přechod z impulsu do vyčerpání.

### A06 Decelerating Correction

- Cena vytváří nové correction low, ale `|return|/ATR`, range nebo volume klesá dvě session za sebou.
- Trigger: close v horní třetině denního range nebo higher close.
- Vyšší kvalita, pokud současně klesá negativní delta response.

### A07 Failed Breakdown

- Low prorazí minimum posledních 5/10/20 session.
- Dokončený bar zavře zpět nad předchozí minimum.
- Entry: následující open nebo stop nad high reversal baru.
- Invalidation: pod sweep low.

### A08 Outside Reversal Day

- Low pod předchozí low, high nad předchozí high, close v horních 25–40 % range.
- Musí mu předcházet definovaná korekce, jinak jde o běžný široký bar.
- Filtry: volume percentile, delta flip, VWAP/VAL location.

### A09 Inside-Day Compression After Selloff

- Pokles alespoň X ATR za 3–5 dnů, poté inside day s range pod mediánem.
- Entry stop nad inside-day high; SL pod korekční low.
- Hypotéza: komprese ukazuje dočasnou rovnováhu po nuceném prodeji.

### A10 Higher-Low Confirmation

- Po correction low přijde bounce, pullback nevytvoří nové low a close se vrátí nad short MA/VWAP.
- Pomalejší vstup s menším falling-knife rizikem.
- Samostatně měřit cenu za potvrzení: horší entry versus menší stop-out rate.

### A11 Gap-Down Recovery

- RTH open pod předchozím close o 0,5/1/1,5 ATR.
- Varianty triggeru: návrat nad open, polovinu gapu nebo předchozí close.
- Rozdělit overnight shock a pokračování předchozího downtrend režimu.

### A12 Correction Low Retest

- První low, rally 1–5 session, druhý test v toleranci 0,25/0,5 ATR.
- Kvalita roste, pokud druhý test má menší range, volume nebo negativní delta.
- Vstup po reclaim lokálního POC/VWAP nebo high trigger baru.

## B. Drawdown a historická anatomie korekcí

### B01 Drawdown Ladder

- Stavy: −2 %, −3 %, −5 %, −7,5 %, −10 %, −15 %, −20 % od rolling peak.
- Každá úroveň je samostatná hypotéza, ne automatické průměrování bez limitu.
- Entry vyžaduje stabilizační trigger; velikost pozice nesmí mechanicky růst do neomezeného propadu.

### B02 Drawdown Velocity

- Stejných −5 % za 3 dny versus za 30 dní jsou rozdílné korekce.
- Veličiny: drawdown depth / sessions from peak; ATR-normalized velocity.
- Fast shock hledá bounce; slow grind čeká trendový reclaim.

### B03 Time-Under-Water

- Kombinuje hloubku drawdownu a počet session od peak.
- Hypotéza: dlouhá mělká korekce se chová jinak než krátký crash.
- Trigger: hazard návratu nad short MA nebo correction midpoint.

### B04 Recovery Fraction

- Po prvním low měřit návrat 25/38,2/50/61,8 % correction range.
- Entry na prvním pullbacku po potvrzeném recovery, nikoli mechanicky na Fibonacci úrovni.
- Exit: retest peak, anchored VWAP nebo časový limit.

### B05 Correction Archetype

- `V`: hluboký rychlý pokles, okamžitý reclaim.
- `W`: první bounce, retest low, druhý reclaim.
- `Stair-step`: série lower highs/lows.
- `Sideways repair`: propad a dlouhá balance.
- Klasifikace musí používat pouze dosud viděnou část korekce; label výsledného tvaru slouží jen pro trénink.

### B06 Historical Correction Analog

- Feature vector při rozhodnutí: depth, duration, velocity, ATR percentile, run-down, gap share, volume percentile, MA slopes, VWAP distance, delta response.
- Najít k nejbližších minulých stavů pouze v training window.
- Výstup není buy/sell, ale empirické odhady `P(TP before SL)`, medián max adverse excursion, medián max favorable excursion a čas do recovery.
- Použít expanding/rolling history a purge minimálně délky maximálního holdingu.

### B07 Conditional Recovery Hazard

- Pro každý den korekce odhadnout pravděpodobnost, že během příštích 5/10/20 session dojde k návratu nad correction midpoint, MA20 nebo předchozí peak dříve než k dalšímu −X ATR.
- Vstup jen pokud odhad po transaction costs překročí break-even pravděpodobnost daného RRR.
- Kalibraci hodnotit Brier scorem a reliability diagramem, ne jen P&L.

### B08 Correction Memory

- Porovnat současnou korekci s posledními 1/3/5 korekcemi podobné volatility.
- Testovat, zda nedávné rychlé V-recovery vedou k přecenění stejného scénáře a horšímu následnému výsledku.
- Slouží jako feature, ne jako samostatná jistota.

## C. RSI, MA a momentum-reversal hybridy

### C01 RSI2 Bull Pullback

- Close nad rostoucí MA200, RSI2 pod 5/10/15.
- Trigger: RSI otočí nahoru nebo close překročí high předchozího dne.
- Neplést nízké RSI s potvrzeným dnem korekce.

### C02 Cumulative RSI Exhaustion

- Součet RSI2 za 2/3 dny pod rolling percentilem.
- Přidat podmínku, že poslední pokles ceny je menší než předchozí navzdory stejně nízkému RSI.

### C03 RSI Price Divergence

- Cena udělá nové 5/10denní low, RSI2/3 vytvoří vyšší low.
- Pivot musí být potvrzen bez repaintingu; alternativně použít fixní srovnání `t` proti `t-k`.
- Trigger: close nad high divergence baru.

### C04 MA Distance Snapback

- `DistanceMA(10/20/50)` pod −0,5/−1/−1,5/−2 ATR.
- Režim: MA50/200 slope, nikoli jen cena nad/pod MA.
- Target: MA, weekly VWAP nebo R multiple; porovnat přirozený a fixní target.

### C05 MA Stack Pullback

- `MA20 > MA50 > MA200`, sklony kladné.
- Korekce se dotkne MA20/50, ale close se vrátí nad ni.
- Invalidation: rozpad stacku nebo close pod MA50/200 podle horizontu.

### C06 Short-MA Reclaim After Weakness

- Weakness splněna předem; následně close zdola překříží SMA3/5/10.
- Toto je vstupní timing, ne samostatná edge.
- Měřit, kolik edge ztratíme čekáním na potvrzení versus kolik stopů odstraníme.

### C07 Double Seven / Channel Reversal

- V bull režimu vstup po 7/10denním low; přirozený exit na 7/10denním high.
- Vedle toho testovat ochranný ATR stop a max hold.
- Délky představují okolí parametrů; nevybírat izolovaný nejlepší den.

### C08 Momentum Failure

- Cena udělá nové low, ale 3/5denní momentum, RSI a distance-to-MA se zlepší.
- Požadovat alespoň dvě nezávislé dimenze; RSI a stejné momentum nejsou plně nezávislé.

## D. VWAP a rovnovážná cena

### D01 Weekly VWAP Deviation

- Close pod weekly VWAP o 1/1,5/2 rolling VWAP SD.
- Varianty: vstup ihned versus reclaim spodního pásma.
- Nový týden resetuje anchor; pondělní signály se hodnotí zvlášť.

### D02 Monthly VWAP Deviation

- Stejný princip na měsíční kotvě.
- Vhodnější pro hlubší multi-week korekce; vstup může škálovat pouze podle předem určených pásem a celkového risk capu.

### D03 Multi-Anchor Confluence

- Cena současně pod weekly VWAP a poblíž monthly/quarterly VWAP nebo anchored VWAP minulého swing low.
- Hypotéza: několik skupin účastníků má podobnou referenční cenu.
- Zakázat anchor vybraný až po znalosti budoucího dna.

### D04 VWAP Undercut and Reclaim

- Cena zavře pod VWAP/pásmem a následující dokončená session zpět nad ním.
- Stop pod sweep low; target VWAP/upper band/previous high.
- Oddělit cenu, která pouze protne VWAP intrabar, od akceptace nad ním.

### D05 Correction-Anchored VWAP

- Anchor vznikne první session, která ex ante splní `ATRShock` nebo breakout correction state.
- Entry při prvním reclaim AVWAP; exit při ztrátě AVWAP nebo recovery targetu.
- Anchor nesmí být ručně posunut na zpětně známé minimum.

### D06 Event-Anchored VWAP

- Předem známé události: CPI/FOMC/NFP nebo začátek gap shock session.
- Vyžaduje archivovaný event calendar; bez něj pouze shock-anchor varianta.
- Testovat zvlášť, protože event risk mění distribuci gapů a fills.

## E. Value Area, POC a auction failure

Tyto systémy vyžadují skutečný Sierra VAP export.

### E01 Prior VAL Sweep Reclaim

- Low pod předchozí RTH VAL o minimálně X ticks/0,1 ATR.
- Dokončený bar/session zavře zpět nad VAL.
- Kvalita: menší druhý sell impulse, pozitivní delta divergence, close nad developing POC.

### E02 Below-VAL Rejection

- Cena stráví pod VAL méně než N minut/barů a vrátí se do value.
- Odlišit krátký rejection od acceptance pod value.
- Entry po návratu; stop pod rejection extreme; target POC/VAH.

### E03 VAL Acceptance Failure

- Nejprve N barů nebo X % volume pod VAL, potom návrat nad VAL a retest shora.
- Testuje uvězněné shorty po neúspěšné akceptaci.

### E04 POC Migration Up During Flat/Lower Price

- Cena stagnuje nebo dělá nižší low, ale session/developing POC roste.
- Hypotéza: obchodní aktivita přijímá vyšší ceny navzdory slabému close.
- Trigger: reclaim lokálního high/VWAP.

### E05 Multi-Day Value Overlap

- Poslední 2–4 value areas se výrazně překrývají; následný downside excursion je odmítnut.
- Target opačná strana composite value.
- Balance musí být vypočtena z minulých dokončených profiles.

### E06 Low-Volume Node Rejection

- Korekce vstoupí do předem existujícího LVN a rychle se vrátí.
- VAP node se fixuje před vstupem, nesmí se dopočítat včetně budoucího objemu.

### E07 Naked POC / Prior HVN Magnet

- Po slabosti leží nad cenou neotestovaný prior POC/HVN.
- Slouží spíše jako target než jako vstupní edge.
- Testovat pravděpodobnost touch před stopem a čas do touch.

## F. Delta exhaustion, absorption a effort-versus-result

Výzkum order flow v S&P 500 futures podporuje vztah mezi order flow a krátkodobou cenou, ale zároveň ukazuje stavovou závislost a možnost reverze dlouhodobého dopadu. Proto delta není sama o sobě buy signál.

### F01 Delta Z-Score Exhaustion

- `DeltaZ(20/60)` pod −1/−1,5/−2/−3.
- Vstup pouze pokud je cena na definované correction location a close není na absolutním low.
- Porovnat okamžitý vstup a delta-flip confirmation.

### F02 Price-Delta Divergence

- Cena udělá nižší low, CVD za 3/5/10 intervalů vyšší low.
- Používat fixní lookback nebo kauzálně potvrzené pivoty.
- Trigger: price reclaim, nikoli samotná divergence.

### F03 Effort Without Result

- Extrémně negativní delta nebo sell volume, ale malý dodatečný pokles ceny.
- Skóre: `abs(negative delta z) / max(downward ticks, floor)`; winsorize denominator.
- Silnější na předem definovaném VAL, weekly VWAP band nebo correction low.

### F04 Absorption at Low

- Velké bid-traded volume na spodních price levels, ale low se neposouvá proporcionálně.
- Požadovat opakování ve 2–3 barových blocích nebo delta flip.
- Vyžaduje VAP/Numbers Bars data, nikoli jen denní delta.

### F05 Delta Climax and Flip

- Bar A má extrémní negativní delta a široký range.
- Bar B nedělá významné nové low a delta se zlepší/přejde do kladné.
- Entry nad high B nebo při VWAP reclaim.

### F06 CVD Down, Price Holds

- CVD vytvoří nové low za N intervalů, cena nikoli.
- Možná pasivní absorpce; potvrdit následným higher high nebo POC migration.
- Opak: cena nové low, CVD drží = slábnoucí agresivní prodej.

### F07 Selling Efficiency Collapse

- Rolling regrese price change na signed delta/order flow.
- Po období záporného toku začne absolutní beta klesat: stejný sell flow posouvá cenu méně.
- Vstup až při změně ceny nahoru; model musí být rolling bez future fitting.

### F08 Delta Breadth Across Timeframes

- Denní korekce + pozitivní delta flip na 30/60min + stabilizace na RTH session.
- Časové rámce musí používat uzavřené bary a jednotný timezone/session template.
- Testovat, zda multi-timeframe filtr skutečně zlepšuje expectancy, ne jen snižuje počet obchodů.

### F09 Failed Negative-Delta Continuation

- Po extrémně negativní session další session nedokáže překonat low navzdory opět záporné deltě.
- Entry při breaku předchozího high nebo reclaim POC.
- Logika: opakovaný agresivní prodej nenachází pokračování.

## G. Kombinované correction engines

### G01 Weakness + Location + Trigger

- Weakness: `RunDown≥3` nebo `CumRet(5)` v dolním 5% rolling percentilu.
- Location: bull200 a pod weekly VWAP/MA20.
- Trigger: close nad prior high nebo weekly VWAP reclaim.
- Jde o základní třívrstvý model s interpretovatelnými komponentami.

### G02 Drawdown + Delta Exhaustion + VAL Reclaim

- Drawdown alespoň 3–5 % od peak.
- Delta effort/result v extrémním percentilu.
- Sweep a reclaim prior VAL.
- Kandidát pro hlubší correction swing; vyžaduje VAP.

### G03 Two-Stage Entry

- Stage 1: slabost a historická recovery probability nad prahem.
- Stage 2: konkrétní price/delta reclaim.
- Signál expiruje po N session; starý oversold stav nesmí aktivovat pozdní vstup.

### G04 Scale-In by Independent Evidence

- Tranche 1 pouze po weakness+location.
- Tranche 2 po exhaustion.
- Tranche 3 po reclaim.
- Každá další tranche musí mít samostatný risk budget; celkový stop a max gross limit jsou pevné. Nejde o martingale podle ztráty.

### G05 Core Long + Tactical Correction Overlay

- Long-term S&P exposure tvoří core.
- Overlay přidává expozici pouze v kvalifikovaných korekcích nebo ji snižuje při failed correction.
- Hlavní test: `Core + Overlay − Core` při stejném kapitálu, nákladech, collateral yield a risk limitu.

### G06 Correction Recovery Trail

- Po úspěšném bounce část pozice zavřít na equilibrium targetu; zbytek držet trailingem pod rising short MA/weekly VWAP.
- Testovat jako předem definovaný exit profil, ne ručně vybíraný z nejhezčích obchodů.

### G07 Failed Correction Long → Defensive Exit

- Long korekční setup selže: nové low, bez delta exhaustion a acceptance pod VAL/MA200.
- Neobracet automaticky short. Nejprve snížit/zavřít core overlay.
- Samostatný short vyžaduje vlastní potvrzenou edge.

### G08 Bear-Market Rally Short

- Bear200, klesající MA, rally k weekly/monthly VWAP nebo MA20/50, RSI2>90, následný failed reclaim.
- Vstup short až po failure triggeru; stop nad rally high.
- Důležitá protiváha long mean-reversion portfolia, ale historicky nízký počet režimů.

## H. Historický correction model z 16 let dat

Historická databáze korekcí nemá ukládat pouze vítězné příklady. Každý rozhodovací den musí být observation row.

### Definice epizody

- Peak vzniká na rolling max známém v daný okamžik.
- Correction start: drawdown překročí předem definovaný práh nebo ATR shock state.
- Trough lze pro popis epizody označit až zpětně, ale live feature nesmí vědět, že šlo o trough.
- Episode end: recovery nad předchozí peak, timeout nebo nový strukturální režim.

### Tabulka každého rozhodovacího stavu

```text
timestamp
depth_pct, depth_atr, duration, velocity
run_down, cumulative_returns_2_3_5_10
gap_component, rth_component
atr_percentile, volume_percentile
ma20_50_200_distance_and_slope
weekly_monthly_anchored_vwap_distance
VAL_VAH_POC_features_when_available
delta_z, CVD_3_5_10, price_response_to_delta
future_MAE_5_10_20, future_MFE_5_10_20
target_before_stop, sessions_to_target, sessions_to_recovery
```

Future sloupce jsou pouze labels. Nikdy nevstupují do features.

### Pravděpodobnostní výstup

Pro každou kandidátní strategii chceme před vstupem znát:

- `P(TP before SL | current state)`.
- `P(positive net P&L after costs)`.
- distribuci MAE a MFE, ne jen průměr.
- očekávaný počet session v obchodě.
- pravděpodobnost, že korekce přejde do hlubšího drawdown bucketu.
- kalibraci pravděpodobností podle decilů.

První implementace má být interpretable: bucketed empirical model nebo regularizovaná logistická regrese. k-NN analog engine může sloužit jako druhý nezávislý odhad. Složitější ML se povolí jen pokud překoná jednoduchý model v nested walk-forward a zůstane kalibrovaný.

### Rozdělení historie

- Expanding nebo rolling training, nikdy náhodný shuffle.
- Purge a embargo minimálně maximální holding period.
- Výběr parametrů uvnitř training fold; hodnocení na následujícím období.
- Roky 2022–2026 už nejsou čistý blind holdout, protože jsme je opakovaně sledovali.
- Po zmrazení musí následovat nový paper-forward interval.

Šestnáct let obsahuje jen několik skutečných krizových režimů. Počet denních řádků není počet nezávislých korekcí. Intervaly nejistoty musí respektovat clustering obchodů ve stejné epizodě.

## Entry engine

Každá strategie vybírá jeden testovaný profil:

| ID | Entry |
|---|---|
| E0 | další RTH open po dokončeném signálu |
| E1 | stop nad high trigger baru |
| E2 | close/reclaim definované úrovně |
| E3 | limit pullback 0,25 ATR po confirmation |
| E4 | retest MA/VWAP/VAL shora |
| E5 | dvoustupňový vstup weakness → confirmation |

Limit/stop signál musí mít pevnou expiraci. Nevyplněný limit se nesmí dodatečně změnit na market bez samostatně testovaného pravidla.

## Exit engine

- Structural invalidation: correction low, sweep low, VAL acceptance nebo trend breakdown.
- ATR stop: 0,75–3 ATR, zmrazený při vstupu.
- Equilibrium target: MA, VWAP, POC, correction midpoint.
- Recovery target: prior high/peak nebo VAH.
- R target: 0,5/1/1,5/2/3R.
- Time stop: 3/5/10/15/20 completed sessions.
- Break-even až po skutečném MFE triggeru; musí zahrnout náklady.
- Trailing se může zpřísnit, nikdy uvolnit; nový level platí až následující tick/bar podle implementace.
- Partial exit je samostatný profil a musí respektovat integer ES/MES quantities.

## Portfolio rolí, nikoli hromada korelovaných strategií

```text
Role 1: Shallow pullback       A01/C01/D01
Role 2: Deep correction       B01/B06/G02
Role 3: Auction rejection     E01/E02/E04
Role 4: Delta exhaustion      F03/F05/F09
Role 5: Trend continuation    C05/D04
Role 6: Bear defense          G07/G08
Role 7: Core overlay          G05
```

Controller nesmí současně přijmout pět verzí téhož IBS signálu jako pět nezávislých sázek. Každá role má family exposure cap; uvnitř role vybere nejlepší předem schválený intent nebo rozdělí pevný risk budget.

## Priorita implementace a testů

### Wave 1: lze testovat na současných datech

1. A01/A03/A04/A05/A06/A07/A09/A10/A11/A12.
2. B01/B02/B03/B04/B05/B06/B07.
3. C01–C08.
4. D01–D05.
5. F01/F02/F03/F05/F06/F07/F09 z období s validní deltou.
6. G01/G03/G05/G06/G07/G08.

### Wave 2: vyžaduje Sierra VAP export

1. E01–E07.
2. F04 a přesnější effort/result po price levels.
3. G02.

### Wave 3: až po jednoduchých modelech

1. Kalibrovaný analog engine B06.
2. Hazard model B07.
3. Correction archetype B05 jako kauzální klasifikátor.
4. Multi-timeframe delta breadth F08.

## Tvrdé vyřazovací podmínky

Strategie se do Sierra live registru nedostane, pokud:

- zisk pochází z jediné korekční epizody;
- sousední hodnoty parametrů jsou převážně ztrátové;
- neprojde stresovými náklady a horším fill modelem;
- výsledek zmizí při posunu vstupu o jeden bar;
- používá VAP, kalendář nebo pivot data, která v okamžiku rozhodnutí nebyla známá;
- nemá dost obchodů nebo nezávislých correction clusters;
- korekce za mnoho provedených pokusů odstraní statistickou významnost;
- poráží B&H pouze díky vyšší expozici;
- Sierra replay neodpovídá výzkumnému ledgeru obchod po obchodu;
- měníme pravidla po prohlédnutí posledního období a stejné období znovu nazveme OOS.

## Sierra Settings bez překročení 128 Inputs

Strategie budou rozděleny podle rolí, ne všechny v jednom monolitu:

```text
Lukacino_GlobalController       portfolio, order management, risk
Lukacino_WeaknessPack           A01–A12
Lukacino_CorrectionModelPack    B01–B08
Lukacino_RSI_MAPack             C01–C08
Lukacino_VWAPPack               D01–D06
Lukacino_ValueAreaPack          E01–E07
Lukacino_DeltaPack              F01–F09
Lukacino_ConfluencePack         G01–G08
Lukacino_EntryExitProfiles      sdílené E/X profily
```

Každý systém má šest základních Inputs: `Enabled`, `Direction`, `Risk Weight`, `Signal Preset`, `Entry Profile`, `Exit Profile`. Pack s maximálně 10 strategiemi spotřebuje 60 Inputs; dalších přibližně 25–35 slouží pro pack-level data, režimy a custom override. Cílový strop je 100 Inputs na studii, 28 indexů zůstává jako rezerva. Nové Inputs se přidávají pouze na konec; zrušené indexy zůstanou `Reserved`.

## Výzkumné zdroje

- Studie intradenních reversalů na S&P 500 futures uvádí reversals po velkých pohybech na open v dlouhém patnáctiletém vzorku: [Intraday price reversals in the US stock index futures market](https://www.sciencedirect.com/science/article/pii/S0378426604000949).
- Vztah order flow a S&P 500 futures ceny je krátkodobě silný, dlouhodobý dopad může být mírně záporný a závisí na stavu trhu: [Order imbalance, liquidity and market returns](https://www.sciencedirect.com/science/article/abs/pii/S0304405X07000633).
- Drawdown má vedle hloubky také trvání a persistence; čas od peak/trough je samostatná informace: [Ups and (draw) downs](https://doi.org/10.1016/j.ijforecast.2025.07.008).
- Dlouhá historie tržních drawdownů ukazuje fat tails a dlouhé recovery, což je důvod nehodnotit strategii jen přes průměr a volatilitu: [CFA Research Foundation SBBI summary](https://rpc.cfainstitute.org/sites/default/files/-/media/documents/book/rf-publication/2020/rf-sbbi-summary-edition.pdf).

Tyto zdroje podporují zkoumání hypotéz, nikoli ziskovost konkrétních pravidel. Každé pravidlo musí projít naším vlastním kauzálním testem, náklady a korekcí za vícenásobné pokusy.
