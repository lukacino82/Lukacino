"""Jen LONG, SL 20 b., RRR 1,5:1 / 2:1 / 3:1, X = 10–40.
Vstup: open + X (stop order) / open − X (limitka), v RTH do 15:59.
Výstup: (a) TP/SL, nejpozději v 16:00; (b) TP/SL bez časového limitu (drží přes noc).
Srovnání: náhodný long (náhodný čas v RTH), stejné SL/TP/výstup, 30 opakování.
Data musí být back-adjustovaná (roly)."""
import sys, os
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
sys.path.insert(0, os.path.dirname(__file__))
from open_fade import load_bars

DATA = sys.argv[1]; OUT = sys.argv[2] if len(sys.argv) > 2 else "reports/open_fade/long_combo"
os.makedirs(OUT, exist_ok=True)
COST, PV, SL, SEEDS = 0.5, 50.0, 20.0, 30
RRR = {"1,5:1": 30.0, "2:1": 40.0, "3:1": 60.0}
XS = [10, 15, 20, 30, 40]
ENTRY = {"momentum": "LONG open + X (stop)", "fade": "LONG open − X (limit)"}
EXIT = {"eod": "výstup nejpozději 16:00", "hold": "drží do TP/SL (přes noc)"}

df = load_bars(DATA)
O, H, L, C = (df[k].values for k in ("open", "high", "low", "close")); TS = df.index; N = len(df)
tm = np.array(TS.time); t0, t_last, t_end = pd.Timestamp("09:30").time(), pd.Timestamp("15:59").time(), pd.Timestamp("16:00").time()
rth_idx = np.flatnonzero([(x >= t0) and (x < t_end) for x in tm])
days = []  # (datum, první RTH bar, poslední RTH bar, poslední bar pro vstup)
for d, grp in pd.Series(rth_idx, index=TS.normalize()[rth_idx]).groupby(level=0):
    ii = grp.values
    if TS[ii[-1]].time() >= pd.Timestamp("15:45").time():
        last_in = ii[np.flatnonzero(tm[ii] <= t_last)[-1]]
        days.append((d, ii[0], ii[-1], last_in))

def find_exit(i, entry, stop, tgt, tp_on_entry_bar, end):
    """end = index posledního baru (16:00 varianta) nebo N-1 (držení)."""
    if L[i] <= stop: return i, stop, "SL"
    if tp_on_entry_bar and H[i] >= tgt: return i, tgt, "TP"
    j = i + 1; CH = 20000
    while j <= end:
        k = min(end + 1, j + CH)
        o, h, l = O[j:k], H[j:k], L[j:k]
        hit = (o <= stop) | (o >= tgt) | (l <= stop) | (h >= tgt)
        if hit.any():
            m = int(np.argmax(hit)); jj = j + m
            if o[m] <= stop: return jj, o[m], "SL"
            if o[m] >= tgt: return jj, o[m], "TP"
            if l[m] <= stop: return jj, stop, "SL"     # SL i TP na stejném baru -> SL
            return jj, tgt, "TP"
        j = k
    return end, C[end], ("EOD" if end < N - 1 else "OPEN")

def run(entry_fn, exit_mode, tp, tp_on_entry):
    out = []; busy = -1
    for d, a, b, last_in in days:
        if a <= busy: continue
        e = entry_fn(a, last_in)
        if e is None: continue
        i, px = e
        j, xp, res = find_exit(i, px, px - SL, px + tp, tp_on_entry, b if exit_mode == "eod" else N - 1)
        busy = j
        out.append((d, TS[i], TS[j], res, xp - px - COST))
    return pd.DataFrame(out, columns=["date", "entry_time", "exit_time", "result", "pts"])

def level_entry(mode, x):
    def f(a, last_in):
        lvl = O[a] + x if mode == "momentum" else O[a] - x
        seg = H[a:last_in + 1] >= lvl if mode == "momentum" else L[a:last_in + 1] <= lvl
        if not seg.any(): return None
        i = a + int(np.argmax(seg))
        return i, (max(lvl, O[i]) if mode == "momentum" else min(lvl, O[i]))
    return f

def random_entry(rng):
    return lambda a, last_in: (lambda i: (i, O[i]))(int(rng.integers(a, last_in + 1)))

rows, trades, bench, bench_curves = [], [], {}, {}
all_dates = pd.DatetimeIndex([d for d, *_ in days])
for ex in EXIT:
    for rr, tp in RRR.items():
        for mode in ENTRY:
            for x in XS:
                tr = run(level_entry(mode, x), ex, tp, mode == "momentum")
                tr["exit"], tr["rrr"], tr["mode"], tr["X"] = ex, rr, mode, x; trades.append(tr)
                p = tr.pts; eq = (p * PV).cumsum(); yrs = p.groupby(tr.date.dt.year).sum()
                rows.append(dict(vystup=ex, RRR=rr, vstup=mode, X=x, obchodu=len(tr),
                                 TP=int((tr.result == "TP").sum()), SL=int((tr.result == "SL").sum()),
                                 EOD=int((tr.result == "EOD").sum()), b_obchod=p.mean(),
                                 t=p.mean() / p.std() * np.sqrt(len(p)), usd=eq.iloc[-1],
                                 maxdd=(eq - eq.cummax()).min(), kladne_roky=f"{(yrs > 0).sum()}/{len(yrs)}"))
        # náhodný long
        finals, curves = [], []
        for s in range(SEEDS):
            tr = run(random_entry(np.random.default_rng(s)), ex, tp, True)
            finals.append(tr.pts.sum() * PV)
            curves.append((tr.pts * PV).groupby(tr.exit_time.dt.normalize()).sum().cumsum()
                          .reindex(all_dates, method="ffill").fillna(0))
        bench[(ex, rr)] = (np.mean(finals), np.quantile(finals, .05), np.quantile(finals, .95))
        bench_curves[(ex, rr)] = pd.concat(curves, axis=1).mean(axis=1)
        print(ex, rr, "hotovo; náhodný long průměr", round(bench[(ex, rr)][0]), flush=True)

R = pd.DataFrame(rows)
R["nahodny_long_usd"] = [bench[(r.vystup, r.RRR)][0] for r in R.itertuples()]
R["nad_nahodou_usd"] = R.usd - R.nahodny_long_usd
R.to_csv(f"{OUT}/souhrn.csv", index=False); T = pd.concat(trades)
pd.set_option("display.width", 250); print(R.round(2).to_string(index=False))

# ---------------- heatmapa ----------------
INK, MUTED, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
XCOL = {10: "#2a78d6", 15: "#eb6834", 20: "#1baf7a", 30: "#e87ba4", 40: "#eda100"}
plt.rcParams.update({"font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": MUTED, "xtick.color": MUTED,
                     "ytick.color": MUTED, "figure.facecolor": SURF, "axes.facecolor": SURF})
usd = lambda v: ("−" if v < 0 else "+") + f"${abs(v)/1000:,.1f}k"
cmap = LinearSegmentedColormap.from_list("div", ["#e34948", "#f0efec", "#2a78d6"]); lim = R.usd.abs().max()
fig, axes = plt.subplots(2, 2, figsize=(17, 13.5))
for r_, ex in enumerate(EXIT):
    for c_, mode in enumerate(ENTRY):
        ax = axes[r_, c_]; sub = R[(R.vystup == ex) & (R.vstup == mode)]
        M = sub.pivot(index="X", columns="RRR", values="usd").loc[XS, list(RRR)]
        ax.imshow(M.values, cmap=cmap, norm=TwoSlopeNorm(0, -lim, lim), aspect="auto")
        for i, x in enumerate(XS):
            for j, rr in enumerate(RRR):
                row = sub[(sub.X == x) & (sub.RRR == rr)].iloc[0]
                ax.text(j, i - 0.22, usd(row.usd), ha="center", va="center", fontsize=11.5, weight="bold", color=INK)
                ax.text(j, i + 0.08, f"t {row.t:+.1f} · {row.obchodu} obch.", ha="center", va="center", fontsize=8.5, color=MUTED)
                ax.text(j, i + 0.3, f"vs. náhodný long {usd(row.nad_nahodou_usd)}", ha="center", va="center", fontsize=8.5, color=MUTED)
        ax.set_xticks(range(len(RRR)), [f"RRR {k}\nTP {v:.0f} / SL 20 b.\nnáhodný long {usd(bench[(ex, k)][0])}" for k, v in RRR.items()])
        ax.set_yticks(range(len(XS)), [f"X = {x}" for x in XS])
        ax.set_xticks(np.arange(-.5, len(RRR)), minor=True); ax.set_yticks(np.arange(-.5, len(XS)), minor=True)
        ax.grid(which="minor", color=SURF, lw=3); ax.tick_params(which="minor", length=0)
        for s in ax.spines.values(): s.set_visible(False)
        ax.set_title(f"{ENTRY[mode]} · {EXIT[ex]}", loc="left", color=INK, fontsize=12)
fig.suptitle("ES jen LONG, SL 20 b. · všech 60 kombinací · čistý výsledek 07/2016–07/2026 po nákladech 0,5 b./obchod (1 ES)\n"
             "modrá = zisk · červená = ztráta · „vs. náhodný long“ = rozdíl proti náhodnému vstupu se stejnými pravidly (průměr 30 běhů)",
             x=0.01, ha="left", color=INK, fontsize=12.5)
fig.tight_layout(rect=(0, 0, 1, 0.95)); fig.savefig(f"{OUT}/heatmapa_vse.png", dpi=140); plt.close(fig)

# ---------------- equity 4 × 3 ----------------
curves = {k: (g.pts * PV).groupby(g.exit_time).sum().cumsum() for k, g in T.groupby(["exit", "mode", "rrr", "X"])}
lo = min(min(c.min() for c in curves.values()), min(c.min() for c in bench_curves.values()))
hi = max(max(c.max() for c in curves.values()), max(c.max() for c in bench_curves.values()))
gap = (hi - lo) * 0.04
fig, axes = plt.subplots(4, 3, figsize=(18, 19), sharex=True, sharey=True)
for r_, (ex, mode) in enumerate([(e, m) for e in EXIT for m in ENTRY]):
    for c_, rr in enumerate(RRR):
        ax = axes[r_, c_]; ends = []
        bc = bench_curves[(ex, rr)]
        ax.plot(bc.index, bc.values, color=MUTED, lw=1.6, ls="--", label="náhodný long (průměr)")
        ends.append([bc.iloc[-1], "náhoda", MUTED])
        for x in XS:
            eq = curves[(ex, mode, rr, x)]; ax.plot(eq.index, eq.values, color=XCOL[x], lw=1.5, label=f"X = {x}")
            ends.append([eq.iloc[-1], f"X={x}", XCOL[x]])
        ends.sort(key=lambda e: e[0]); ys = [e[0] for e in ends]
        for k in range(1, len(ys)): ys[k] = max(ys[k], ys[k - 1] + gap)
        xend = all_dates[-1]
        for (v, lab, col), yl in zip(ends, ys):
            ax.plot([xend], [yl], marker="s", ms=4, color=col, clip_on=False)
            ax.annotate(f"{lab}: {usd(v)}", (xend, yl), xytext=(5, 0), textcoords="offset points", fontsize=8, color=INK, va="center")
        ax.axhline(0, color=MUTED, lw=1); ax.grid(axis="y", color=GRID, lw=.8)
        for s in ("top", "right"): ax.spines[s].set_visible(False)
        ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: ("−" if v < 0 else "") + f"${abs(v)/1000:,.0f}k"))
        ax.xaxis.set_major_locator(mdates.YearLocator(2)); ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        ax.set_title(f"{ENTRY[mode]} · {EXIT[ex]}\nRRR {rr} (TP {RRR[rr]:.0f} / SL 20 b.)", loc="left", fontsize=10, color=INK)
axes[0, 0].legend(frameon=False, loc="upper left", fontsize=8.5, ncol=2); axes[0, 0].set_ylim(lo * 1.1, hi * 1.2)
fig.suptitle("ES jen LONG, SL 20 b. · equity po nákladech 0,5 b./obchod, 1 ES, 07/2016–07/2026 · šedá čárkovaná = náhodný long se stejnými pravidly",
             x=0.01, ha="left", color=INK, fontsize=13)
fig.tight_layout(rect=(0, 0, 0.95, 0.97)); fig.subplots_adjust(wspace=0.28)
fig.savefig(f"{OUT}/equity_vse.png", dpi=120); plt.close(fig)
