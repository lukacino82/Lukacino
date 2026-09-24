"""Popisné metriky ES + equity dvou kandidátů vs. stejná šablona každý den (IS/OOS vyznačeno)."""
import sys, os
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
import matplotlib.dates as mdates
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "open_fade"))
from open_fade import load_bars
OUT = "reports/patterns"
R = pd.read_pickle(f"{OUT}/sablony_R.pkl"); F = pd.read_pickle(f"{OUT}/vlastnosti.pkl"); D = pd.read_pickle(f"{OUT}/dny.pkl")
# ---- popisné metriky
D["up"] = D.h - D.o; D["down"] = D.o - D.l
desc = pd.DataFrame({k: [D[c].mean(), D[c].median(), D[c].quantile(.25), D[c].quantile(.75), D[c].quantile(.9)]
                     for k, c in (("rozpětí H−L", "rng"), ("propad pod open O−L", "down"), ("růst nad open H−O", "up"))},
                    index=["průměr", "medián", "25 %", "75 %", "90 %"]).T.round(1)
m = D.rng.mean()
share = pd.Series({"pod průměrem": (D.rng < m).mean(), "průměr ±10 %": ((D.rng >= .9*m) & (D.rng <= 1.1*m)).mean(),
                   "nad průměrem": (D.rng > m).mean()}).mul(100).round(1)
bars = load_bars(sys.argv[1]); t = bars.index.time
rth = bars[(t >= pd.Timestamp("09:30").time()) & (t < pd.Timestamp("16:00").time())]
b30 = rth.groupby([rth.index.normalize(), rth.index.floor("30min").time]).agg(h=("high", "max"), l=("low", "min"))
slot = (b30.h - b30.l).groupby(level=1).mean().round(1)
slot.index = [x.strftime("%H:%M") for x in slot.index]
print(desc.to_string()); print(share.to_string()); print(slot.to_string())
desc.to_csv(f"{OUT}/metriky_dne.csv"); slot.to_csv(f"{OUT}/rozpeti_30min.csv")
# ---- equity kandidátů v $ (R × SL v bodech × $50)
CANDS = [("open−0,25ATR | SL 0.25ATR | RRR 1.5:1 | 16:00", "včera close-close < −0,5 ATR", 0.25,
          "A) Nákup poklesu po silném poklesovém dni\nvčera close-close < −0,5 ATR → limitka open − 0,25 ATR, SL 0,25 ATR, TP 1,5×SL, výstup 16:00"),
         ("open | SL 0.25ATR | RRR 1:1 | drží≤10d", "pondělí", 0.25,
          "B) Pondělní long\npondělí → long na open, SL 0,25 ATR, TP 1×SL, drží do TP/SL (max 10 dní)")]
INK, MUTED, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
plt.rcParams.update({"font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED,
                     "axes.spines.top": False, "axes.spines.right": False, "figure.facecolor": SURF, "axes.facecolor": SURF})
fmt = matplotlib.ticker.FuncFormatter(lambda v, _: ("−" if v < 0 else "") + f"${abs(v)/1000:,.0f}k")
usd = lambda v: ("−" if v < 0 else "+") + f"${abs(v)/1000:,.1f}k"
fig, axes = plt.subplots(2, 1, figsize=(14, 10.5), sharex=True)
for ax, (tname, f, slk, title) in zip(axes, CANDS):
    usdR = R[tname] * slk * D.atr * 50
    sel = usdR[F[f]].dropna(); allr = usdR.dropna()
    scale = len(sel) / len(allr)   # „každý den“ přepočtený na stejný počet obchodů
    e1 = sel.cumsum(); e2 = (allr * scale).cumsum()
    ax.axvspan(pd.Timestamp("2022-01-01"), D.index[-1], color="#cde2fb", alpha=.45, lw=0)
    ax.text(pd.Timestamp("2022-02-01"), 0.97, "OOS 2022–2026: data, která hledání neviděla", transform=ax.get_xaxis_transform(),
            fontsize=9, color=INK, va="top")
    ax.text(pd.Timestamp("2016-09-01"), 0.97, "hledání 2016–2021", transform=ax.get_xaxis_transform(), fontsize=9, color=INK, va="top")
    ax.plot(e1.index, e1.values, color="#2a78d6", lw=2.2, label=f"vzorec ({len(sel)} obchodů): {usd(e1.iloc[-1])}")
    ax.plot(e2.index, e2.values, color=MUTED, lw=1.6, ls="--", label=f"stejná šablona každý den, přepočteno na stejný počet obchodů: {usd(e2.iloc[-1])}")
    oos = sel[sel.index >= "2022"]
    ax.set_title(title + f"\nOOS: {len(oos)} obchodů, {usd(oos.sum())}, t = {oos.mean()/oos.std()*np.sqrt(len(oos)):.2f}",
                 loc="left", color=INK, fontsize=10.5)
    ax.axhline(0, color=MUTED, lw=1); ax.grid(axis="y", color=GRID, lw=.8); ax.yaxis.set_major_formatter(fmt)
    ax.legend(frameon=False, loc="lower right", fontsize=9)
axes[-1].xaxis.set_major_locator(mdates.YearLocator(1)); axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
fig.suptitle("ES: dva kandidáti, kteří přežili validaci mimo vzorek · 1 ES, po nákladech 0,5 b./obchod", x=0.01, ha="left", color=INK, fontsize=12.5)
fig.tight_layout(rect=(0, 0, 1, 0.96)); fig.savefig(f"{OUT}/kandidati.png", dpi=140)
