"""Souhrnný přehled brainstormingu → reports/brainstorm/PREHLED.md (z CSV, která vytvoří ostatní skripty)."""
import pandas as pd
c = lambda v, d=2: "–" if pd.isna(v) else f"{v:.{d}f}".replace(".", ",").replace("-", "−")
D = "reports/brainstorm/"
L = ["# Brainstorming: hledání dalších systémů s hranou na ES (07/2016–07/2026)\n",
     "Data: volume bary z Excelu (vč. bid/ask objemu = delta), rozhodnutí v 15:58 ET, náklady 0,5 b. na obchod. "
     "Skripty `analysis/brainstorm/`: `features.py` (denní tabulka), `hypotheses.py` (kola 1–5, `ROUND=1..5`), `exposure.py`, "
     "`portfolio.py`, `report.py`. Grafy: `equity_systemy.png`, `ucet.png`.\n",
     "**Kritéria:** mechanismus předem, málo parametrů; **p** = jak často stejná pravidla v náhodné dny (bez podmínky) vyjdou stejně "
     "dobře (2 000×); **alfa t** = t úseku regrese denního P&L na denní pohyb ES; kladné v 2016–21 i 2022–26; sousední parametry "
     "kladné. Celkem ~70 variant, takže nejlepší t čistě náhodou ≈ √(2·ln 70) ≈ 2,9.\n"]
names = {"1": "Kolo 1: IBS, série poklesů, noc, intradenní momentum, gap fade, VWAP, panika, short v medvědím trhu, delta, stop-run, přelom měsíce",
         "2": "Kolo 2: kalendář a toky (týdenní reverze, víkend, svátky, FOMC, opční expirace, N-denní low, reverze na konci dne)",
         "3": "Kolo 3: order flow a objem (absorpce, kapitulace, rebalancing, reverzní den)",
         "4": "Kolo 4: mimo seanci (znovuotevření Globexu, Evropa)",
         "5_base": "Kolo 5: robustnost kandidátů (základ)", "5_cost1": "Kolo 5: dvojnásobné náklady 1 b.",
         "5_c1600": "Kolo 5: rozhodnutí 16:00"}
for key, title in names.items():
    R = pd.read_csv(f"{D}hypotezy_kolo{key}.csv")
    L += [f"\n## {title}\n", "| Rodina | Varianta | Obchodů | b./obchod | t | p (náhoda) | alfa t | 2016–21 t | 2022–26 t |",
          "|---|---|---|---|---|---|---|---|---|"]
    for _, r in R.iterrows():
        L.append(f"| {r.rodina} | {r.varianta} | {int(r.obchodu)} | {c(r.get('b_obchod'), 1)} | {c(r.get('t'))} | "
                 f"{c(r.get('p_nahoda'), 3)} | {c(r.get('alfa_t'))} | {c(r.get('is_t'))} | {c(r.get('oos_t'))} |")
E = pd.read_csv(f"{D}expozice.csv")
L += ["\n## Řízení expozice (volatility timing, MA200)\n", "| Varianta | Sharpe | Max DD (b.) | alfa t | beta |", "|---|---|---|---|---|"]
for _, r in E.iterrows(): L.append(f"| {r.varianta} | {c(r.sharpe)} | {c(r.maxdd_b, 0)} | {c(r.alfa_t)} | {c(r.beta)} |")
P = pd.read_csv(f"{D}portfolio.csv"); K = pd.read_csv(f"{D}korelace.csv", index_col=0); A = pd.read_csv(f"{D}ucet.csv")
L += ["\n## Portfolio kandidátů (každý systém 1 ES, 05/2017–07/2026)\n",
      "| Systém | Zisk | Sharpe | Max DD (b.) | alfa (b./rok) | alfa t | beta | Sharpe 16–21 / 22–26 | V trhu |", "|---|---|---|---|---|---|---|---|---|"]
for _, r in P.iterrows():
    L.append(f"| {r.system} | ${r.usd_1es/1000:,.0f}k | {c(r.sharpe)} | {c(r.maxdd_b, 0)} | {c(r.alfa_b_rok, 0)} | {c(r.alfa_t)} | "
             f"{c(r.beta)} | {c(r.sharpe_2016_21)} / {c(r.sharpe_2022_26)} | {c(r.v_trhu_pct, 0)} % |")
L += ["\n**Korelace denního P&L:**\n", "| | " + " | ".join(K.columns) + " |", "|---" * (len(K.columns) + 1) + "|"]
for i, r in K.iterrows(): L.append(f"| {i} | " + " | ".join(c(v) for v in r.values) + " |")
L += ["\n## Simulace účtu $50 000 v MES (reinvestice, páka na systém)\n", "| Plán | Konec | CAGR | Max DD |", "|---|---|---|---|"]
for _, r in A.iterrows(): L.append(f"| {r.plan} | ${r.konec:,.0f} | {c(r.cagr, 1)} % | {c(r.maxdd, 0)} % |")
L += ["\n## Závěr\n", "| Systém | Hodnocení | Proč |", "|---|---|---|",
      "| RSI(2) < 10 nad MA200 | **silný** | pravidla z literatury (2008), p 0,004, t 3,6, obě období, robustní na čas i náklady |",
      "| 3 nižší close → do 1. vyššího close | **silný (nový)** | t 4,85 nad prahem 2,9, p < 0,001, alfa t 2,9, obě období, 3 různé výstupy t 3,8–4,9, rozhodnutí 16:00 t 3,4; 56 % obchodů mimo pozice RSI(2) má t 4,2 |",
      "| Absorpce short (pokles + delta > 0 → short 1 den) | **zkušební** | p ≤ 0,01 ve všech variantách, alfa t 2,4–3,9, záporná korelace s ostatními (−0,2 až −0,3); ale nalezeno a posteriori (otočení výsledku z kola 1) a t na obchod jen 1,5–2 |",
      "| Kapitulační objem 1,6–1,8× | **zkušební** | p 0,004–0,012, obě období kladná, ale 1,4× a 2× slabé (úzké plató), alfa t 1,3 pod prahem |",
      "| VAL swing | **slabý** | alfa t 0,55, beta 0,54 = hlavně expozice trhu; p 0,21 proti náhodě |",
      "| Ostatní (~55 variant) | zamítnuto | intradenní momentum, VWAP reverze, gap fade, noc, FOMC, expirace, svátky, víkend, Globex, Evropa, rebalancing, panika, delta long |",
      "\nPortfolio RSI(2) + 3 poklesy + absorpce + kapitulace (bez VAL): Sharpe 1,39 proti 0,66 u buy & hold, alfa t 3,8, beta 0,21. "
      "Tři z těchto systémů byly vybrány z ~70 variant na stejných datech, takže skutečný budoucí výsledek bude nižší. Nutný forward test."]
open(f"{D}PREHLED.md", "w").write("\n".join(L) + "\n")
print("ok")
