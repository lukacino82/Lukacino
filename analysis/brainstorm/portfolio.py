"""Portfolio kandidátů z brainstormingu + RSI(2) a VAL swing: korelace, alfa proti trhu, simulace účtu.

Každý systém = vlastní kontrakt, max. 1 pozice. Denní přecenění na close 15:58.
python analysis/brainstorm/portfolio.py <denní .pkl> <složka bs> <složka buy_weakness> <výstupní složka>
"""
import sys, os
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter, FixedLocator, NullLocator

F = pd.read_pickle(sys.argv[1]); BS, BW, OUT = sys.argv[2], sys.argv[3], sys.argv[4]
os.makedirs(OUT, exist_ok=True)
c = F.c1558.values; N = len(c); dates = F.index; pos = pd.Series(np.arange(N), index=dates)
mkt = np.r_[0, np.diff(c)]; COST = 0.5; WARM = 201
T5 = pd.read_pickle(os.path.join(BS, "_trades_kolo5_base.pkl"))
TB = pd.read_pickle(os.path.join(BW, "_trades.pkl"))

def from_bw(t):
    return [(int(pos[r.entry_d]), int(pos[r.exit_d]), r.pts, 1) for _, r in t.iterrows()]

SYS = {  # název: (obchody (k, j, pnl, směr), barva, hodnocení)
    "RSI(2) < 10 nad MA200": (T5["1 RSI(2) | RSI(2) < 10 nad MA200 → do close > MA5 (max 10)"], "#eb6834"),
    "3 nižší close": (T5["2 Série poklesů | 3 nižší close → do 1. vyššího close (max 10)"], "#2a78d6"),
    "VAL swing": (from_bw(TB["VAL swing (výzkum: bez stopu, max 10 dní)"]), "#1baf7a"),
    "Kapitulační objem 1,6×": (T5["3 Kapitulační objem | pokles a objem > 1.6× průměr 20 dní → do close > včerejší high (max 5)"], "#eda100"),
    "Absorpce short": (T5["4 Absorpce short | pokles a delta > 0 → short 1 den/dny"], "#e87ba4"),
}

def daily(tr):
    P = np.zeros(N); inm = np.zeros(N, bool)
    for k, j, pnl, d in tr:
        for m in range(k + 1, j + 1): P[m] += d * (c[m] - c[m - 1]); inm[m] = True
        P[j] -= COST
    return P, inm

D = {n: daily(v[0]) for n, v in SYS.items()}
PNL = pd.DataFrame({n: v[0] for n, v in D.items()}, index=dates).iloc[WARM:]
PNL["Portfolio (všech 5)"] = PNL.sum(axis=1)
PNL["Portfolio bez VAL"] = PNL.drop(columns=["VAL swing", "Portfolio (všech 5)"]).sum(axis=1)
m = mkt[WARM:]
def stats(y):
    X = np.c_[np.ones(len(m)), m]; b, *_ = np.linalg.lstsq(X, y, rcond=None); r = y - X @ b
    se = np.sqrt(r.var(ddof=2) * np.linalg.inv(X.T @ X)[0, 0]); eq = np.cumsum(y)
    sh = y.mean() / y.std() * np.sqrt(252); yr = dates[WARM:].year
    return dict(body=eq[-1], usd_1es=eq[-1] * 50, sharpe=sh, maxdd_b=(eq - np.maximum.accumulate(eq)).min(),
                alfa_b_rok=b[0] * 252, alfa_t=b[0] / se, beta=b[1],
                sharpe_2016_21=y[yr < 2022].mean() / y[yr < 2022].std() * np.sqrt(252),
                sharpe_2022_26=y[yr >= 2022].mean() / y[yr >= 2022].std() * np.sqrt(252),
                kladne_roky=f"{(pd.Series(y, index=yr).groupby(level=0).sum() > 0).sum()}/{len(set(yr))}")
rows = []
for col in PNL.columns:
    s = stats(PNL[col].values); s["system"] = col
    s["v_trhu_pct"] = D[col][1][WARM:].mean() * 100 if col in D else np.nan
    rows.append(s)
s = stats(m); s["system"] = "Buy & hold 1 ES"; s["v_trhu_pct"] = 100; rows.append(s)
R = pd.DataFrame(rows).set_index("system"); R.round(3).to_csv(os.path.join(OUT, "portfolio.csv"))
CORR = PNL[list(SYS)].corr().round(2); CORR.to_csv(os.path.join(OUT, "korelace.csv"))
pd.set_option("display.width", 250); print(R.round(2).to_string()); print(CORR)

# ---------- graf 1: equity na 1 ES za systém
INK, SEC, MUTED, GRID, SURF = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#fcfcfb"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
def style(ax):
    ax.set_facecolor(SURF); ax.grid(axis="y", color=GRID, lw=0.8); ax.set_axisbelow(True)
    for sp in ("top", "right"): ax.spines[sp].set_visible(False)
    for sp in ("left", "bottom"): ax.spines[sp].set_color(GRID)
    ax.tick_params(colors=MUTED)
idx = dates[WARM:]
fig, (a1, a2) = plt.subplots(1, 2, figsize=(17, 6.2), gridspec_kw={"wspace": 0.12})
fig.patch.set_facecolor(SURF); style(a1); style(a2)
for n, (tr, col) in SYS.items():
    r = R.loc[n]
    a1.plot(idx, PNL[n].cumsum() * 50 / 1000, color=col, lw=1.8,
            label=f"{n}: {r.usd_1es/1000:+,.0f}k, alfa t {r.alfa_t:.2f}, v trhu {r.v_trhu_pct:.0f} %".replace(".", ","))
a1.axhline(0, color=MUTED, lw=.8); a1.legend(frameon=False, labelcolor=SEC, fontsize=8.8, loc="upper left")
a1.set_title("Jednotlivé systémy, každý 1 ES", loc="left", color=INK, fontweight="bold")
a1.set_ylabel("Kumulativní zisk (tis. $)", color=SEC)
for col, colr, lw in (("Portfolio (všech 5)", "#4a3aa7", 2.4), ("Portfolio bez VAL", "#2a78d6", 1.8)):
    r = R.loc[col]
    a2.plot(idx, PNL[col].cumsum() * 50 / 1000, color=colr, lw=lw,
            label=f"{col}: {r.usd_1es/1000:+,.0f}k, Sharpe {r.sharpe:.2f}, max DD {r.maxdd_b*50/1000:,.0f}k".replace(".", ","))
r = R.loc["Buy & hold 1 ES"]
a2.plot(idx, np.cumsum(m) * 50 / 1000, color=MUTED, lw=1.5, ls="--",
        label=f"Buy & hold 1 ES: {r.usd_1es/1000:+,.0f}k, Sharpe {r.sharpe:.2f}, max DD {r.maxdd_b*50/1000:,.0f}k".replace(".", ","))
a2.axhline(0, color=MUTED, lw=.8); a2.legend(frameon=False, labelcolor=SEC, fontsize=8.8, loc="upper left")
a2.set_title("Portfolio (součet kontraktů) proti trhu", loc="left", color=INK, fontweight="bold")
for a in (a1, a2):
    a.xaxis.set_major_locator(mdates.YearLocator(1)); a.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
fig.suptitle("ES 05/2017–07/2026 (po zahřátí MA200) · rozhodnutí 15:58 · náklady 0,5 b. na obchod",
             x=0.125, ha="left", color=INK, fontsize=12.5, fontweight="bold", y=1.0)
fig.savefig(os.path.join(OUT, "equity_systemy.png"), dpi=150, bbox_inches="tight", facecolor=SURF); plt.close(fig)

# ---------- graf 2: účet v MES
def account(names, lev, start=50_000.0, brakes=()):
    eq, peak = start, start; open_q = {}; curve = []
    tr_by = {n: {k: (j, d) for k, j, p, d in SYS[n][0]} for n in names}
    for t in range(WARM, N):
        day = 0.0
        for n in names:
            if n in open_q:
                q, j, d = open_q[n]; day += q * 5 * d * (c[t] - c[t - 1])
                if t == j: day -= q * 5 * COST; del open_q[n]
        eq += day; peak = max(peak, eq); curve.append(eq)
        mult = 1.0
        for lvl, mm in brakes:
            if eq / peak - 1 <= lvl: mult = mm
        for n in names:
            if n not in open_q and t in tr_by[n]:
                j, d = tr_by[n][t]; q = int(np.floor(eq * lev * mult / (c[t] * 5)))
                if q >= 1 and j > t: open_q[n] = (q, j, d)
    return pd.Series(curve, index=idx)
PL = [("Konzervativní: 5 systémů, páka 0,5× na systém", list(SYS), 0.5, (), "#1baf7a"),
      ("Střední: 5 systémů, páka 1× na systém", list(SYS), 1.0, (), "#2a78d6"),
      ("Agresivní: 5 systémů, páka 2× na systém, brzdy −20 %/−30 %", list(SYS), 2.0, ((-0.2, 0.5), (-0.3, 0.25)), "#4a3aa7")]
fig, (ax, ax2) = plt.subplots(2, 1, figsize=(13, 8.2), sharex=True, gridspec_kw={"height_ratios": [3, 1.2], "hspace": 0.08})
fig.patch.set_facecolor(SURF); style(ax); style(ax2); acc = []
yrs = (idx[-1] - idx[0]).days / 365.25
for lab, names, lev, br, col in PL:
    s = account(names, lev, brakes=br); dd = s / s.cummax() - 1; cagr = (s.iloc[-1] / 50_000) ** (1 / yrs) - 1
    ax.plot(idx, s / 1000, color=col, lw=2, label=f"{lab}: ${s.iloc[-1]/1000:,.0f}k, CAGR {cagr*100:.1f} %, max DD {dd.min()*100:.0f} %".replace(".", ","))
    ax2.plot(idx, dd * 100, color=col, lw=1.2); acc.append(dict(plan=lab, konec=s.iloc[-1], cagr=cagr * 100, maxdd=dd.min() * 100))
bh = 50_000 * c[WARM:] / c[WARM]; ddb = bh / np.maximum.accumulate(bh) - 1
cb = (bh[-1] / 50_000) ** (1 / yrs) - 1
ax.plot(idx, bh / 1000, color=MUTED, lw=1.4, ls="--", label=f"Buy & hold páka 1×: ${bh[-1]/1000:,.0f}k, CAGR {cb*100:.1f} %, max DD {ddb.min()*100:.0f} %".replace(".", ","))
ax2.plot(idx, ddb * 100, color=MUTED, lw=1, ls="--"); acc.append(dict(plan="Buy & hold 1×", konec=bh[-1], cagr=cb * 100, maxdd=ddb.min() * 100))
ax.set_yscale("log"); ax.yaxis.set_major_locator(FixedLocator([40, 50, 75, 100, 150, 200, 300, 400, 600, 1000, 1500, 2000])); ax.yaxis.set_minor_locator(NullLocator())
ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v/1000:.1f}M".replace(".", ",") if v >= 1000 else f"${v:.0f}k")); ax.set_ylabel("Účet (log. osa)", color=SEC)
ax.legend(frameon=False, labelcolor=SEC, fontsize=9, loc="upper left"); ax2.set_ylabel("Drawdown (%)", color=SEC)
ax2.xaxis.set_major_locator(mdates.YearLocator(1)); ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
ax.set_title("Simulace účtu $50 000 v MES, reinvestice · páka = hodnota kontraktů systému / účet", loc="left", color=INK, fontweight="bold")
fig.savefig(os.path.join(OUT, "ucet.png"), dpi=150, bbox_inches="tight", facecolor=SURF)
pd.DataFrame(acc).round(2).to_csv(os.path.join(OUT, "ucet.csv"), index=False); print(pd.DataFrame(acc).round(1))
