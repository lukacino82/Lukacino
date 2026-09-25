"""Grafy a přehled k testu „Lukacino Buy Weakness“ (výstup backtest.py).

1) equity_1es.png: VAL swing, RSI(2) a Obě na 1 ES + pásmo náhodných vstupů se stejným držením
2) ucet.png: simulace účtu $50k v MES, konzervativní (páka 1×) vs. agresivní (páka 3× + brzdy DD)

python analysis/buy_weakness/report.py <složka s výsledky backtest.py>
"""
import sys, os
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
import matplotlib.dates as mdates

OUT = sys.argv[1]
D = pd.read_pickle(os.path.join(OUT, "_daily.pkl")); T = pd.read_pickle(os.path.join(OUT, "_trades.pkl"))
R = pd.read_csv(os.path.join(OUT, "varianty.csv"))
COST, PV, MES = 0.5, 50.0, 5.0
c = D.c.values; N = len(c)
INK, SEC, MUTED, GRID, SURF, BAND = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#fcfcfb", "#d9d8d2"
COL = {"VAL": "#2a78d6", "RSI": "#eb6834", "BOTH": "#1baf7a"}
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
money = lambda v: ("−" if v < 0 else "+") + "$" + f"{abs(v)/1000:,.1f}".replace(".", ",") + "k"

def style(ax):
    ax.set_facecolor(SURF); ax.grid(axis="y", color=GRID, lw=0.8); ax.set_axisbelow(True)
    for sp in ("top", "right"): ax.spines[sp].set_visible(False)
    for sp in ("left", "bottom"): ax.spines[sp].set_color(GRID)
    ax.tick_params(colors=MUTED)

MAIN = [("VAL", "VAL swing (výzkum: bez stopu, max 10 dní)", "VAL swing: close < VAL → long do close > POC"),
        ("RSI", "RSI(2)<10 nad MA200 (výzkum)", "RSI(2) < 10 nad MA200 → long do close > MA5"),
        ("BOTH", "Obě (1 pozice, první signál)", "Obě strategie, 1 pozice")]

# ---------- 1) equity na 1 ES ----------
grid = D.index
fig, axes = plt.subplots(1, 3, figsize=(17, 5.4), sharey=True, gridspec_kw={"wspace": 0.06})
fig.patch.set_facecolor(SURF)
rng = np.random.default_rng(1)
for ax, (key, name, label) in zip(axes, MAIN):
    style(ax); tr = T[name]; h = tr.days.values
    curves = []
    for s in range(200):
        ks = np.sort(rng.integers(15, N - h.max() - 1, len(h)))
        p = (c[ks + h] - c[ks] - COST) * PV
        s_ = pd.Series(p, index=grid[ks + h]).groupby(level=0).sum().cumsum()
        curves.append(s_.reindex(grid).ffill().fillna(0))
    Rn = pd.concat(curves, axis=1)
    ax.fill_between(grid, Rn.quantile(.05, axis=1) / 1000, Rn.quantile(.95, axis=1) / 1000, color=BAND, alpha=.6, lw=0,
                    label="náhodné vstupy, stejné držení (5.–95. perc.)")
    ax.plot(grid, Rn.median(axis=1) / 1000, color=MUTED, lw=1.3, ls="--", label="náhodné vstupy, medián")
    eq = tr.set_index("exit_d").pts.mul(PV).groupby(level=0).sum().cumsum().reindex(grid).ffill().fillna(0)
    ax.plot(grid, eq / 1000, color=COL[key], lw=2.2, label="strategie")
    r = R[R.varianta == name].iloc[0]
    ax.set_title(label, loc="left", color=INK, fontweight="bold", fontsize=10.5, pad=20)
    ax.text(0, 1.012, f"{int(r.obchodu)} obchodů · {r.b_obchod:+.1f} b./obchod · t {r.t:.2f} · nad náhodou "
            f"{r.b_obchod - r.nahoda_b:+.1f} b. (p = {r.p_nahoda:.2f})".replace(".", ",").replace("b,", "b."),
            transform=ax.transAxes, va="bottom", color=SEC, fontsize=8.8)
    ax.axhline(0, color=MUTED, lw=.8)
    ax.xaxis.set_major_locator(mdates.YearLocator(2)); ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.axvspan(pd.Timestamp("2016-07-01"), pd.Timestamp("2018-07-09" if key == "VAL" else "2019-05-01"),
               color="#eb6834", alpha=.06, lw=0)
axes[0].set_ylabel("Kumulativní zisk (tis. $, 1 ES)", color=SEC)
axes[0].legend(frameon=False, labelcolor=SEC, fontsize=8.5, loc="upper left")
fig.suptitle("Buy Weakness na ES 07/2016–07/2026 · rozhodnutí 15:58, náklady 0,5 b. · podbarvení = data, která původní výzkum neviděl",
             x=0.125, ha="left", color=INK, fontsize=12.5, fontweight="bold", y=1.03)
fig.savefig(os.path.join(OUT, "equity_1es.png"), dpi=150, bbox_inches="tight", facecolor=SURF)
plt.close(fig)

# ---------- 2) simulace účtu v MES ----------
def account(tr, lev, start=50_000.0, brakes=()):
    eq = start; peak = start; out = [(D.index[0], eq)]; rows = []
    for _, t in tr.sort_values("entry_d").iterrows():
        dd = eq / peak - 1; mult = 1.0
        for lvl, m in brakes:
            if dd <= lvl: mult = m
        qty = int(np.floor(eq * lev * mult / (t.entry * MES)))
        if qty < 1: out.append((t.exit_d, eq)); continue
        pnl = qty * MES * t.pts / t.qty if t.qty else 0
        eq += pnl; peak = max(peak, eq); out.append((t.exit_d, eq)); rows.append(qty)
    s = pd.Series([v for _, v in out], index=[d for d, _ in out]).groupby(level=0).last()
    return s.reindex(grid).ffill().bfill(), rows

PLANS = [("Konzervativní: RSI(2), páka 1×", "RSI(2)<10 nad MA200 (výzkum)", 1.0, (), "#eb6834"),
         ("Konzervativní: Obě, páka 1×", "Obě (1 pozice, první signál)", 1.0, (), "#1baf7a"),
         ("Agresivní: Obě, páka 3×, brzdy −20 %/−30 %", "Obě (1 pozice, první signál)", 3.0,
          ((-0.20, 0.5), (-0.30, 0.25)), "#4a3aa7")]
fig, (ax, ax2) = plt.subplots(2, 1, figsize=(13, 8), sharex=True, gridspec_kw={"height_ratios": [3, 1.2], "hspace": 0.08})
fig.patch.set_facecolor(SURF); style(ax); style(ax2)
lines = []
for label, name, lev, br, col in PLANS:
    s, q = account(T[name], lev, brakes=br)
    yrs = (grid[-1] - grid[0]).days / 365.25; cagr = (s.iloc[-1] / s.iloc[0]) ** (1 / yrs) - 1
    dd = s / s.cummax() - 1
    ax.plot(grid, s / 1000, color=col, lw=2, label=f"{label}: ${s.iloc[-1]/1000:,.0f}k, CAGR {cagr*100:.1f} %, max DD {dd.min()*100:.0f} %".replace(".", ","))
    ax2.plot(grid, dd * 100, color=col, lw=1.2)
    lines.append(dict(plan=label, konec=s.iloc[-1], cagr=cagr * 100, maxdd=dd.min() * 100, mes_median=np.median(q) if q else 0))
bh = 50_000 * c / c[0]
ax.plot(grid, bh / 1000, color=MUTED, lw=1.3, ls="--", label=f"Buy & hold (páka 1×): ${bh[-1]/1000:,.0f}k, max DD {((bh/np.maximum.accumulate(bh))-1).min()*100:.0f} %".replace(".", ","))
ax2.plot(grid, (bh / np.maximum.accumulate(bh) - 1) * 100, color=MUTED, lw=1, ls="--")
ax.set_yscale("log"); ax.set_ylabel("Účet (tis. $, log. osa)", color=SEC)
from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator
ax.yaxis.set_major_locator(FixedLocator([40, 50, 60, 80, 100, 125, 150, 200]))
ax.yaxis.set_minor_locator(NullLocator())
ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:.0f}k"))
ax.legend(frameon=False, labelcolor=SEC, fontsize=9, loc="upper left")
ax2.set_ylabel("Drawdown (%)", color=SEC)
ax2.xaxis.set_major_locator(mdates.YearLocator(1)); ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
ax.set_title("Simulace účtu $50 000 v MES: páka = hodnota kontraktů / účet, reinvestice zisku", loc="left",
             color=INK, fontweight="bold", fontsize=12.5)
fig.savefig(os.path.join(OUT, "ucet.png"), dpi=150, bbox_inches="tight", facecolor=SURF)
pd.DataFrame(lines).round(2).to_csv(os.path.join(OUT, "ucet.csv"), index=False)
print(pd.DataFrame(lines).round(1).to_string(index=False))
