"""5 nejlepších 'robotů' (jen LONG, SL 20 b.) obchodují současně na jednom účtu, každý 1 ES.
Portfolio equity = součet uzavřených obchodů všech robotů podle času výstupu.
Srovnání: stejných 5 robotů s náhodným vstupem (průměr 30 běhů)."""
import sys, os
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
import matplotlib.dates as mdates
HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "long_combo.py")).read().split("rows, trades, bench, bench_curves")[0]
sys.argv = [sys.argv[0], sys.argv[1], "/tmp/_robots_ignore"]
ns = {"__file__": os.path.join(HERE, "long_combo.py")}; exec(src, ns)
run, level_entry, random_entry, days = ns["run"], ns["level_entry"], ns["random_entry"], ns["days"]
OUT = "reports/open_fade/roboti"; os.makedirs(OUT, exist_ok=True)
PV = 50.0
ROBOTS = [  # (název, X, TP, výstup)
    ("R1 open+15 · 1,5:1 · drží", 15, 30.0, "hold"),
    ("R2 open+20 · 1,5:1 · drží", 20, 30.0, "hold"),
    ("R3 open+10 · 3:1 · drží", 10, 60.0, "hold"),
    ("R4 open+15 · 1,5:1 · do 16:00", 15, 30.0, "eod"),
    ("R5 open+20 · 2:1 · do 16:00", 20, 40.0, "eod"),
]
all_dates = pd.DatetimeIndex([d for d, *_ in days])
trs, rand_curves = {}, {}
for name, x, tp, ex in ROBOTS:
    tr = run(level_entry("momentum", x), ex, tp, True); tr["robot"] = name; trs[name] = tr
    cs = []
    for s in range(30):
        rt = run(random_entry(np.random.default_rng(s)), ex, tp, True)
        cs.append((rt.pts * PV).groupby(rt.exit_time.dt.normalize()).sum().cumsum().reindex(all_dates, method="ffill").fillna(0))
    rand_curves[name] = pd.concat(cs, axis=1).mean(axis=1)
    print(name, len(tr), round(tr.pts.sum() * PV), flush=True)
T = pd.concat(trs.values(), ignore_index=True)
# kumulace po datech výstupu; obchody uzavřené mimo RTH den (neděle večer, svátek) se přenesou
# do nejbližšího dalšího RTH dne (ffill kumulativní řady), nic se nezahodí
cum = (T.pts * PV).groupby([T.exit_time.dt.normalize(), T.robot]).sum().unstack(fill_value=0).cumsum()
eq = cum.reindex(cum.index.union(all_dates)).ffill().fillna(0).reindex(all_dates)
eq.iloc[-1] = cum.iloc[-1]  # poslední hodnota = úplný součet
daily = eq.diff().fillna(eq.iloc[0])
port = eq.sum(axis=1); rand_port = sum(rand_curves.values())
assert abs(port.iloc[-1] - T.pts.sum() * PV) < 1, "součet portfolia nesedí"
dd = port - port.cummax()
# souběžné pozice (kontrakty otevřené ve stejný okamžik)
ev = pd.concat([pd.Series(1, index=T.entry_time), pd.Series(-1, index=T.exit_time)]).sort_index(kind="stable")
openpos = ev.cumsum(); maxpos = int(openpos.max())
pos_share = openpos.groupby(openpos.values).size() / len(openpos)
# roční výsledky a statistiky
yr = (daily.sum(axis=1)).groupby(all_dates.year).sum()
dret = daily.sum(axis=1)
sharpe = dret.mean() / dret.std() * np.sqrt(252)
corr = daily.corr().values[np.triu_indices(len(ROBOTS), 1)].mean()
underwater = (dd < 0).astype(int); longest = underwater.groupby((underwater == 0).cumsum()).sum().max()
stats = dict(celkem=port.iloc[-1], nahodny_celkem=rand_port.iloc[-1], max_dd=dd.min(), nejdelsi_pod_vrcholem_dni=int(longest),
             sharpe_rocni=sharpe, prum_korelace_robotu=corr, max_soubezne_kontrakty=maxpos, obchodu=len(T),
             ztratove_roky=int((yr < 0).sum()))
print(stats); print(yr.round(0).to_dict()); print({k: round(v.iloc[-1]) for k, v in eq.items()}); pass
pd.Series(stats).to_csv(f"{OUT}/statistiky.csv"); yr.to_csv(f"{OUT}/po_letech.csv")

INK, MUTED, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
COLS = ["#2a78d6", "#eb6834", "#1baf7a", "#e87ba4", "#eda100"]
plt.rcParams.update({"font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED,
                     "axes.spines.top": False, "axes.spines.right": False, "figure.facecolor": SURF, "axes.facecolor": SURF})
fmt = matplotlib.ticker.FuncFormatter(lambda v, _: ("−" if v < 0 else "") + f"${abs(v)/1000:,.0f}k")
usd = lambda v: ("−" if v < 0 else "+") + f"${abs(v)/1000:,.1f}k"
fig, (a1, a2, a3) = plt.subplots(3, 1, figsize=(14, 12.5), height_ratios=[3.2, 1.2, 1.2], sharex=True)
for (name, *_), c in zip(ROBOTS, COLS):
    a1.plot(eq.index, eq[name], color=c, lw=1.1, alpha=.9, label=f"{name}: {usd(eq[name].iloc[-1])}")
a1.plot(port.index, port.values, color=INK, lw=2.6, label=f"PORTFOLIO 5 robotů: {usd(port.iloc[-1])}")
a1.plot(rand_port.index, rand_port.values, color=MUTED, lw=2, ls="--", label=f"5 robotů s náhodným vstupem: {usd(rand_port.iloc[-1])}")
a1.axhline(0, color=MUTED, lw=1); a1.grid(axis="y", color=GRID, lw=.8); a1.yaxis.set_major_formatter(fmt)
a1.legend(frameon=False, loc="upper left", fontsize=9)
a1.set_title(f"5 robotů současně na jednom účtu (každý 1 ES, jen LONG, SL 20 b.), 07/2016–07/2026, po nákladech 0,5 b./obchod\n"
             f"{len(T)} obchodů · max DD {usd(dd.min())} · nejdelší období bez nového maxima {int(longest)} obch. dní · "
             f"Sharpe {sharpe:.2f} · průměrná korelace robotů {corr:.2f}", loc="left", color=INK, fontsize=11)
a2.fill_between(dd.index, dd.values, 0, color="#e34948", alpha=.35, lw=0); a2.plot(dd.index, dd.values, color="#e34948", lw=1)
a2.yaxis.set_major_formatter(fmt); a2.grid(axis="y", color=GRID, lw=.8); a2.set_ylabel("drawdown portfolia")
a2.annotate(f"max {usd(dd.min())}", (dd.idxmin(), dd.min()), xytext=(6, 0), textcoords="offset points", fontsize=9, color=INK)
op = openpos.groupby(openpos.index.normalize()).max().reindex(all_dates).fillna(0)
op20 = op.rolling(20).mean()
a3.fill_between(op20.index, op20.values, 0, color="#2a78d6", alpha=.45, lw=0)
a3.plot(op20.index, op20.values, color="#2a78d6", lw=1.2)
a3.set_ylabel("otevřené kontrakty\n(max za den, 20denní průměr)"); a3.set_ylim(0, maxpos); a3.grid(axis="y", color=GRID, lw=.8)
a3.text(op20.index[5], maxpos * 0.9, f"maximum současně: {maxpos} ES", fontsize=9, color=INK)
a3.xaxis.set_major_locator(mdates.YearLocator(1)); a3.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
fig.tight_layout(); fig.savefig(f"{OUT}/portfolio_robotu.png", dpi=140)
