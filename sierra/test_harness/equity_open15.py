"""Equity křivka studie Lukacino Open-X Range RRR: long open+15, SL 20, RRR 2, Kill = No.
Obchody pocházejí z emulace Replay (main.cpp), benchmark = náhodný long se stejnými
pravidly (vstup v náhodném čase 9:30–15:00, SL 20 / TP 40, drží do TP/SL, max. 1 pozice).

python sierra/test_harness/equity_open15.py <trades.csv z harnessu> <bary .xlsx/.pkl> <výstupní složka>
"""
import sys, os
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
import matplotlib.dates as mdates

TRADES, BARS, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(OUT, exist_ok=True)
COST, PV = 0.5, 50.0
BLUE, INK, SEC, MUTED, GRID, SURF, BAND = "#2a78d6", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#fcfcfb", "#d9d8d2"

# ---- obchody studie ----
t = pd.read_csv(TRADES)
t["pnl"] = ((t.exit - t.entry) * t.dir - COST) * PV
t["xts"] = pd.to_datetime(t.xd.astype(str)) + pd.to_timedelta(t.xt, unit="s")
t["ets"] = pd.to_datetime(t.d.astype(str)) + pd.to_timedelta(t.t, unit="s")
eq = t.set_index("xts").pnl.cumsum()

# ---- náhodný long se stejnými pravidly ----
here = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(here, "..", "..", "open_fade", "long_sl20_hold.py")
src = open(src_path).read().split("def run(")[0]
ns = {"__file__": src_path}
argv = sys.argv; sys.argv = [argv[0], BARS, os.path.join(OUT, "_tmp")]
exec(src, ns); sys.argv = argv
try: os.rmdir(os.path.join(OUT, "_tmp"))
except OSError: pass
days, find_exit, TS, O, tm = ns["days"], ns["find_exit"], ns["TS"], ns["O"], ns["tm"]
t_last = pd.Timestamp("15:00").time()
grid = pd.date_range(eq.index.min().normalize(), TS[-1].normalize(), freq="D")
curves = []
for seed in range(30):
    rng = np.random.default_rng(seed); busy = -1; ex, pn = [], []
    for d, a, b in days:
        if a <= busy: continue
        cand = [i for i in range(a, b + 1) if tm[i] <= t_last]
        i = cand[rng.integers(len(cand))]; e = O[i]
        j, px, r = find_exit(i, e, e - 20.0, e + 40.0, True); busy = j
        ex.append(TS[j]); pn.append((px - e - COST) * PV)
    s = pd.Series(pn, index=pd.DatetimeIndex(ex)).cumsum()
    curves.append(s.groupby(s.index.normalize()).last().reindex(grid).ffill().fillna(0))
R = pd.concat(curves, axis=1)
r_med, r_lo, r_hi = R.median(axis=1), R.quantile(.05, axis=1), R.quantile(.95, axis=1)

# ---- statistiky ----
pnl = t.pnl.values
tstat = pnl.mean() / pnl.std(ddof=1) * np.sqrt(len(pnl))
dd = eq - eq.cummax()
win = pnl > 0
streak = best = 0
for w in win:
    streak = 0 if w else streak + 1; best = max(best, streak)
hold_h = (t.xts - t.ets).dt.total_seconds() / 3600
years = t.groupby(t.xts.dt.year).pnl.agg(["count", "sum"])

# ---- graf ----
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
fig, (ax, ax2) = plt.subplots(2, 1, figsize=(12, 7.2), sharex=True,
                              gridspec_kw={"height_ratios": [3, 1.1], "hspace": 0.08})
fig.patch.set_facecolor(SURF)
for a in (ax, ax2):
    a.set_facecolor(SURF); a.grid(axis="y", color=GRID, lw=0.8); a.set_axisbelow(True)
    for sp in ("top", "right"): a.spines[sp].set_visible(False)
    for sp in ("left", "bottom"): a.spines[sp].set_color(GRID)
    a.tick_params(colors=MUTED)

ax.fill_between(R.index, r_lo / 1000, r_hi / 1000, color=BAND, alpha=0.6, lw=0,
                label="Náhodný long, 5.–95. percentil (30×)")
ax.plot(R.index, r_med / 1000, color=MUTED, lw=1.6, ls="--", label="Náhodný long, medián")
ax.plot(eq.index, eq.values / 1000, color=BLUE, lw=2, label="Studie: long open+15, SL 20, RRR 2, Kill = No")
ax.axhline(0, color=MUTED, lw=0.8)
ax.annotate(f"${eq.iloc[-1]/1000:,.1f}k", (eq.index[-1], eq.iloc[-1] / 1000), xytext=(6, 0),
            textcoords="offset points", va="center", color=INK, fontweight="bold")
gap = 0 if abs(eq.iloc[-1] - r_med.iloc[-1]) > 8000 else (-12 if r_med.iloc[-1] < eq.iloc[-1] else 12)
ax.annotate(f"${r_med.iloc[-1]/1000:,.1f}k", (R.index[-1], r_med.iloc[-1] / 1000), xytext=(6, gap),
            textcoords="offset points", va="center", color=SEC)
ax.set_ylabel("Kumulativní zisk (tis. $, 1 ES)", color=SEC)
ax.legend(loc="upper left", frameon=False, labelcolor=SEC)
ax.set_title("Lukacino Open-X Range RRR: long open+15, SL 20 b., TP 40 b., drží do TP/SL",
             loc="left", color=INK, fontsize=13, fontweight="bold", pad=24)
ax.text(0, 1.02, f"ES 07/2016–07/2026 · {len(t)} obchodů · úspěšnost {win.mean()*100:.1f} % · "
        f"{pnl.mean()/PV:+.2f} b./obchod · t = {tstat:.2f} · max. DD −${-dd.min()/1000:,.1f}k · "
        f"nejdelší série ztrát {best} · náklady 0,5 b./obchod",
        transform=ax.transAxes, color=SEC, fontsize=9.5)

ax2.fill_between(dd.index, dd.values / 1000, 0, color=BLUE, alpha=0.25, lw=0, step="post")
ax2.plot(dd.index, dd.values / 1000, color=BLUE, lw=1, drawstyle="steps-post")
ax2.set_ylabel("Drawdown (tis. $)", color=SEC)
ax2.xaxis.set_major_locator(mdates.YearLocator(1)); ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
fig.savefig(os.path.join(OUT, "equity.png"), dpi=150, bbox_inches="tight", facecolor=SURF)

t.to_csv(os.path.join(OUT, "obchody.csv"), index=False,
         columns=["ets", "xts", "entry", "exit", "why", "pnl"])
with open(os.path.join(OUT, "PREHLED.md"), "w") as f:
    f.write("# Studie Lukacino Open-X Range RRR: long open+15, SL 20, RRR 2, Kill = No\n\n")
    f.write("Obchody z emulace Replay studie (`sierra/test_harness`) na volume barech ES "
            "07/2016–07/2026. Fill na close signálního baru, SL/TP bracket, gap přes SL = fill na open. "
            "1 ES, náklady 0,5 b. na obchod. Graf: `equity.png`, obchody: `obchody.csv`.\n\n")
    f.write("| Metrika | Hodnota |\n|---|---|\n")
    for k, v in [("Obchodů", f"{len(t)}"), ("TP / SL", f"{(t.why=='T').sum()} / {(t.why=='S').sum()}"),
                 ("Úspěšnost", f"{win.mean()*100:.1f} % (break-even 33,3 %)"),
                 ("Čistý zisk", f"${pnl.sum():,.0f}"), ("Bodů na obchod", f"{pnl.mean()/PV:+.2f}"),
                 ("t-statistika", f"{tstat:.2f}"), ("Max. drawdown", f"−${-dd.min():,.0f}"),
                 ("Nejdelší série ztrát", f"{best}"),
                 ("Držení přes noc", f"{(t.xd != t.d).mean()*100:.0f} % obchodů"),
                 ("Držení medián / průměr", f"{hold_h.median():.1f} h / {hold_h.mean():.1f} h"),
                 ("Náhodný long, medián (5.–95. perc.)",
                  f"${r_med.iloc[-1]:,.0f} (${r_lo.iloc[-1]:,.0f} až ${r_hi.iloc[-1]:,.0f})")]:
        f.write(f"| {k} | {v} |\n")
    f.write("\n| Rok | Obchodů | Zisk $ |\n|---|---|---|\n")
    for y, row in years.iterrows():
        f.write(f"| {y} | {int(row['count'])} | {row['sum']:,.0f} |\n")
print(f"n {len(t)} net {pnl.sum():,.0f} t {tstat:.2f} dd {dd.min():,.0f} streak {best} "
      f"random med {r_med.iloc[-1]:,.0f} [{r_lo.iloc[-1]:,.0f}, {r_hi.iloc[-1]:,.0f}]")
print(years)
