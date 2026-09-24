"""Jen LONG, SL 20 b., RRR 2:1 / 3:1, vstup na open+X (stop) nebo open−X (limit) v RTH.
BEZ výstupu v 16:00: pozice drží přes noc i víkendy, dokud nezasáhne TP nebo SL.
Max. 1 otevřená pozice; nový vstup se hledá až v RTH dni po uzavření předchozí.
Data musí být back-adjustovaná (jinak roly kontraktu falešně spouští SL/TP)."""
import sys, os
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
sys.path.insert(0, os.path.dirname(__file__))
from open_fade import load_bars

DATA = sys.argv[1]; OUT = sys.argv[2] if len(sys.argv) > 2 else "reports/open_fade/long_sl20_hold"
os.makedirs(OUT, exist_ok=True)
COST, PV, SL = 0.5, 50.0, 20.0
RRR = {"2:1": 40.0, "3:1": 60.0}
XS = [10, 15, 20, 30, 40]
ENTRY = {"momentum": "LONG na open + X (stop order)", "fade": "LONG na open − X (limitka)"}
df = load_bars(DATA)
O, H, L, C = (df[k].values for k in ("open", "high", "low", "close")); TS = df.index; N = len(df)
tm = TS.time; t0, t_last, t_end = pd.Timestamp("09:30").time(), pd.Timestamp("15:59").time(), pd.Timestamp("16:00").time()
is_rth = np.array([(x >= t0) and (x < t_end) for x in tm])
dates = TS.normalize()
rth_idx = np.flatnonzero(is_rth)
days = []  # (datum, index prvního RTH baru, index posledního baru, kdy smí vstoupit)
for d, grp in pd.Series(rth_idx, index=dates[rth_idx]).groupby(level=0):
    ii = grp.values
    if TS[ii[-1]].time() >= pd.Timestamp("15:45").time(): days.append((d, ii[0], ii[-1]))

def find_exit(i, entry, stop, tgt, tp_on_entry_bar):
    # vstupní bar
    if L[i] <= stop: return i, stop, "SL"
    if tp_on_entry_bar and H[i] >= tgt: return i, tgt, "TP"
    j = i + 1; CH = 20000
    while j < N:
        k = min(N, j + CH)
        o, h, l = O[j:k], H[j:k], L[j:k]
        hit = (o <= stop) | (o >= tgt) | (l <= stop) | (h >= tgt)
        if hit.any():
            m = int(np.argmax(hit)); jj = j + m
            if o[m] <= stop: return jj, o[m], "SL"       # gap přes SL (např. přes noc)
            if o[m] >= tgt: return jj, o[m], "TP"
            if l[m] <= stop: return jj, stop, "SL"       # SL i TP na stejném baru -> SL
            return jj, tgt, "TP"
        j = k
    return N - 1, C[-1], "OPEN"

def run(mode, x, tp):
    out = []; busy = -1
    for d, a, b in days:
        if a <= busy: continue
        o0 = O[a]
        level = o0 + x if mode == "momentum" else o0 - x
        for i in range(a, b + 1):
            if tm[i] > t_last: break
            if mode == "momentum" and H[i] >= level:
                entry = max(level, O[i]); break
            if mode == "fade" and L[i] <= level:
                entry = min(level, O[i]); break
        else:
            continue
        if tm[i] > t_last: continue
        stop, tgt = entry - SL, entry + tp
        j, px, res = find_exit(i, entry, stop, tgt, mode == "momentum")
        busy = j
        out.append(dict(date=d, entry_time=TS[i], exit_time=TS[j], result=res, pts=px - entry - COST,
                        hold_h=(TS[j] - TS[i]).total_seconds() / 3600))
    return pd.DataFrame(out)

rows, trades = [], []
for mode in ENTRY:
    for rr, tp in RRR.items():
        for x in XS:
            tr = run(mode, x, tp); tr["mode"], tr["rrr"], tr["X"] = mode, rr, x; trades.append(tr)
            p = tr.pts; eq = (p * PV).cumsum(); yrs = p.groupby(tr.date.dt.year).sum()
            rows.append(dict(vstup=mode, RRR=rr, X=x, obchodu=len(tr), TP=int((tr.result == "TP").sum()),
                             SL=int((tr.result == "SL").sum()), otevreno=int((tr.result == "OPEN").sum()),
                             TP_pct=100 * (tr.result == "TP").mean(), breakeven=100 * SL / (SL + tp),
                             prum_drzeni_h=tr.hold_h.mean(), median_drzeni_h=tr.hold_h.median(),
                             pres_noc_pct=100 * (tr.exit_time.dt.normalize() > tr.entry_time.dt.normalize()).mean(),
                             b_obchod=p.mean(), t=p.mean() / p.std() * np.sqrt(len(p)), usd=eq.iloc[-1],
                             maxdd=(eq - eq.cummax()).min(), kladne_roky=f"{(yrs > 0).sum()}/{len(yrs)}"))
R = pd.DataFrame(rows); R.to_csv(f"{OUT}/souhrn.csv", index=False); T = pd.concat(trades)
pd.set_option("display.width", 250); print(R.round(2).to_string(index=False))

# ---------- grafy ----------
INK, MUTED, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
XCOL = {10: "#2a78d6", 15: "#eb6834", 20: "#1baf7a", 30: "#e87ba4", 40: "#eda100"}
plt.rcParams.update({"font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": MUTED, "xtick.color": MUTED,
                     "ytick.color": MUTED, "figure.facecolor": SURF, "axes.facecolor": SURF})
usd = lambda v: ("−" if v < 0 else "+") + f"${abs(v)/1000:,.1f}k"
cmap = LinearSegmentedColormap.from_list("div", ["#e34948", "#f0efec", "#2a78d6"]); lim = R.usd.abs().max()
fig, axes = plt.subplots(1, 2, figsize=(13, 6.6))
for ax, mode in zip(axes, ENTRY):
    sub = R[R.vstup == mode]
    M = sub.pivot(index="X", columns="RRR", values="usd").loc[XS, list(RRR)]
    ax.imshow(M.values, cmap=cmap, norm=TwoSlopeNorm(0, -lim, lim), aspect="auto")
    for i, x in enumerate(XS):
        for j, rr in enumerate(RRR):
            row = sub[(sub.X == x) & (sub.RRR == rr)].iloc[0]
            ax.text(j, i - 0.2, usd(row.usd), ha="center", va="center", fontsize=11, weight="bold", color=INK)
            ax.text(j, i + 0.12, f"t {row.t:+.1f} · {row.obchodu} obch.", ha="center", va="center", fontsize=8.5, color=MUTED)
            ax.text(j, i + 0.33, f"TP {row.TP_pct:.0f} % (BE {row.breakeven:.0f} %) · Ø {row.prum_drzeni_h:.0f} h",
                    ha="center", va="center", fontsize=8.5, color=MUTED)
    ax.set_xticks(range(len(RRR)), [f"RRR {k}\nTP {v:.0f} b. / SL 20 b." for k, v in RRR.items()])
    ax.set_yticks(range(len(XS)), [f"X = {x}" for x in XS])
    ax.set_xticks(np.arange(-.5, len(RRR)), minor=True); ax.set_yticks(np.arange(-.5, len(XS)), minor=True)
    ax.grid(which="minor", color=SURF, lw=3); ax.tick_params(which="minor", length=0)
    for s in ax.spines.values(): s.set_visible(False)
    ax.set_title(ENTRY[mode], loc="left", color=INK, fontsize=11.5)
fig.suptitle("ES jen LONG, SL 20 b., BEZ výstupu v 16:00 (drží do TP/SL přes noc): čistý výsledek 07/2016–07/2026, 1 ES, po nákladech\n"
             "modrá = zisk · červená = ztráta · BE = úspěšnost potřebná na nulu · Ø = průměrná doba držení",
             x=0.01, ha="left", color=INK, fontsize=11.5)
fig.tight_layout(rect=(0, 0, 1, 0.92)); fig.savefig(f"{OUT}/heatmapa.png", dpi=150); plt.close(fig)
fig, axes = plt.subplots(2, 2, figsize=(15, 9.5), sharex=True, sharey=True)
curves = {(m_, rr, x): (g.pts * PV).groupby(g.exit_time).sum().cumsum()
          for (m_, rr, x), g in T.groupby(["mode", "rrr", "X"])}
lo = min(c.min() for c in curves.values()); hi = max(c.max() for c in curves.values()); gap = (hi - lo) * 0.045
for r, mode in enumerate(ENTRY):
    for c, rr in enumerate(RRR):
        ax = axes[r, c]; ends = []
        for x in XS:
            eq = curves[(mode, rr, x)]; ax.plot(eq.index, eq.values, color=XCOL[x], lw=1.7, label=f"X = {x}")
            ends.append([eq.iloc[-1], x])
        ends.sort(); ys = [e[0] for e in ends]
        for k in range(1, len(ys)): ys[k] = max(ys[k], ys[k - 1] + gap)
        xend = T.exit_time.max()
        for (v, x), yl in zip(ends, ys):
            ax.plot([xend], [yl], marker="s", ms=4, color=XCOL[x], clip_on=False)
            ax.annotate(f"X={x}: {usd(v)}", (xend, yl), xytext=(5, 0), textcoords="offset points", fontsize=8.5, color=INK, va="center")
        ax.axhline(0, color=MUTED, lw=1); ax.grid(axis="y", color=GRID, lw=.8)
        for s in ("top", "right"): ax.spines[s].set_visible(False)
        ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: ("−" if v < 0 else "") + f"${abs(v)/1000:,.0f}k"))
        ax.xaxis.set_major_locator(mdates.YearLocator(2)); ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        ax.set_title(f"{ENTRY[mode]} · RRR {rr} (TP {RRR[rr]:.0f} b. / SL 20 b.)", loc="left", fontsize=10.5, color=INK)
axes[0, 0].legend(frameon=False, loc="upper left", fontsize=9, ncol=3); axes[0, 0].set_ylim(lo * 1.1 if lo < 0 else -5000, hi * 1.2)
fig.suptitle("ES jen LONG, SL 20 b., BEZ výstupu v 16:00 · equity po nákladech 0,5 b./obchod, 1 ES, 07/2016–07/2026",
             x=0.01, ha="left", color=INK, fontsize=12.5)
fig.tight_layout(rect=(0, 0, 0.95, 0.96)); fig.subplots_adjust(wspace=0.25)
fig.savefig(f"{OUT}/equity.png", dpi=140); plt.close(fig)
