"""Vizuální přehled denního rozpětí, propadu pod open a růstu nad open (ES RTH 09:30–16:00 ET)
vůči průměru + měsíční vývoj průměrů za celé období.

python range_atr/visual_monthly.py <bary .xlsx/.pkl/.txt> [výstupní složka]
Výstupy: rozlozeni_vs_prumer.png, dosah_od_open.png, mesicni_prumery.png, mesicne.csv, MESICNE.md
"""
import sys, os
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
import matplotlib.dates as mdates
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "open_fade"))
from open_fade import load_bars

OUT = sys.argv[2] if len(sys.argv) > 2 else "reports/range_atr/mesicne"
os.makedirs(OUT, exist_ok=True)
df = load_bars(sys.argv[1]); t = df.index.time
rth = df[(t >= pd.Timestamp("09:30").time()) & (t < pd.Timestamp("16:00").time())]
g = rth.groupby(rth.index.date)
d = pd.DataFrame({"o": g.open.first(), "h": g.high.max(), "l": g.low.min(),
                  "last": g.apply(lambda x: x.index[-1].time())})
d = d[d["last"] >= pd.Timestamp("15:45").time()]
d.index = pd.to_datetime(d.index)
d["rng"], d["ol"], d["ho"] = d.h - d.l, d.o - d.l, d.h - d.o
d["atr"] = d.rng.rolling(14).mean().shift(1)          # ATR(14) známé na open
METRICS = [("rng", "Denní rozpětí (High − Low)"), ("ol", "Propad pod open (Open − Low)"),
           ("ho", "Růst nad open (High − Open)")]
BAND = 0.10

# barvy (jedna modrá škála: pod průměrem světlá, průměr, nad průměrem tmavá)
INK, SEC, MUTED, GRID, SURF = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#fcfcfb"
LIGHT, MID, DARK, ORANGE = "#86b6ef", "#2a78d6", "#104281", "#eb6834"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})

def style(ax):
    ax.set_facecolor(SURF); ax.grid(axis="y", color=GRID, lw=0.8); ax.set_axisbelow(True)
    for sp in ("top", "right"): ax.spines[sp].set_visible(False)
    for sp in ("left", "bottom"): ax.spines[sp].set_color(GRID)
    ax.tick_params(colors=MUTED)

fmt = lambda v: f"{v:.1f}".replace(".", ",")

# ---------- 1) rozložení dní vůči průměru ----------
fig, axes = plt.subplots(3, 1, figsize=(12, 11), gridspec_kw={"hspace": 0.55})
fig.patch.set_facecolor(SURF)
for ax, (k, name) in zip(axes, METRICS):
    style(ax); x = d[k]; m = x.mean(); lo, hi = m * (1 - BAND), m * (1 + BAND)
    below, inb, above = x[x < lo], x[(x >= lo) & (x <= hi)], x[x > hi]
    cap = np.percentile(x, 99); bins = np.arange(0, cap + 2.5, 2.5)
    for part, col in ((below, LIGHT), (inb, MID), (above, DARK)):
        ax.hist(part.clip(upper=cap), bins=bins, color=col, edgecolor=SURF, linewidth=0.6)
    top = ax.get_ylim()[1]
    ax.axvline(m, color=INK, lw=1.4); ax.axvline(x.median(), color=MUTED, lw=1.2, ls="--")
    ax.text(m, top * 1.02, f"průměr {fmt(m)}", ha="left", color=INK, fontsize=9, fontweight="bold")
    ax.text(x.median(), top * 1.02, f"medián {fmt(x.median())} ", ha="right", color=SEC, fontsize=9)
    for part, lab, col, fx in ((below, "pod průměrem", LIGHT, 0.60), (above, "nad průměrem", DARK, 0.84)):
        ax.text(fx, 0.62, f"{lab}: {len(part)} dní ({len(part)/len(x)*100:.0f} %)\nprůměr těchto dní {fmt(part.mean())} b.",
                transform=ax.transAxes, ha="center", color=SEC, fontsize=9,
                bbox=dict(boxstyle="round,pad=0.4", fc=SURF, ec=col, lw=1.6))
    ax.annotate(f"v průměru ±10 %: {len(inb)} dní ({len(inb)/len(x)*100:.0f} %)", (m, top * 0.88),
                xytext=(8, 0), textcoords="offset points", color=SEC, fontsize=9)
    ax.set_title(name, loc="left", color=INK, fontweight="bold", pad=16)
    ax.set_xlim(0, cap); ax.set_ylabel("Počet dní", color=SEC)
axes[-1].set_xlabel("Body (dny nad 99. percentilem sečteny do posledního sloupce)", color=SEC)
fig.suptitle(f"ES RTH 09:30–16:00, {len(d)} dní ({d.index[0]:%m/%Y}–{d.index[-1]:%m/%Y}): rozložení dní vůči průměru",
             x=0.125, ha="left", color=INK, fontsize=13, fontweight="bold", y=0.95)
fig.savefig(os.path.join(OUT, "rozlozeni_vs_prumer.png"), dpi=150, bbox_inches="tight", facecolor=SURF)
plt.close(fig)

# ---------- 2) jak často cena od open dojde aspoň na X (pro TP/SL) ----------
fig, (a1, a2) = plt.subplots(1, 2, figsize=(14, 5.6), gridspec_kw={"wspace": 0.18})
fig.patch.set_facecolor(SURF)
xs = np.arange(0, 101, 1)
for ax, unit in ((a1, "pts"), (a2, "atr")):
    style(ax)
    dd = d if unit == "pts" else d.dropna(subset=["atr"])
    grid = xs if unit == "pts" else np.linspace(0, 2, 101)
    for k, lab, col in (("ho", "nahoru od open (High − Open)", MID), ("ol", "dolů od open (Open − Low)", ORANGE)):
        v = dd[k].values if unit == "pts" else (dd[k] / dd.atr).values
        p = [(v >= q).mean() * 100 for q in grid]
        ax.plot(grid, p, color=col, lw=2, label=lab)
    # typické TP/SL: body na křivkách + tabulka hodnot pod grafem (bez popisků v grafu)
    marks = (10, 15, 20, 30, 40, 60) if unit == "pts" else (0.25, 0.5, 0.75, 1.0)
    cells = []
    for k, col in (("ho", MID), ("ol", ORANGE)):
        v = dd[k].values if unit == "pts" else (dd[k] / dd.atr).values
        row = []
        for q in marks:
            pv = (v >= q).mean() * 100
            ax.plot([q], [pv], "o", ms=5, color=col, mec=SURF, mew=1.5, zorder=3)
            row.append(f"{pv:.0f} %")
        cells.append(row)
    for q in marks:
        ax.axvline(q, color=GRID, lw=0.8, zorder=0)
    head = [f"{q} b." for q in marks] if unit == "pts" else [f"{q}×ATR".replace(".", ",") for q in marks]
    tb = ax.table(cellText=cells, rowLabels=["nahoru ≥ X", "dolů ≥ X"], colLabels=head,
                  cellLoc="center", bbox=[0.0, -0.42, 1.0, 0.24])
    tb.auto_set_font_size(False); tb.set_fontsize(9)
    for (r, c_), cell in tb.get_celld().items():
        cell.set_edgecolor(GRID); cell.set_facecolor(SURF)
        cell.get_text().set_color(INK if r == 0 else (MID if r == 1 else ORANGE) if c_ >= 0 else SEC)
    ax.set_ylim(0, 100); ax.set_ylabel("% dní, kdy cena od open došla aspoň na X", color=SEC)
    ax.legend(frameon=False, labelcolor=SEC, loc="upper right")
a1.set_xlabel("X v bodech", color=SEC); a1.set_xlim(0, 100)
a1.set_title("V bodech (celé období)", loc="left", color=INK, fontweight="bold")
a2.set_xlabel("X jako násobek ATR(14) známého na open", color=SEC); a2.set_xlim(0, 2)
a2.set_title("Jako násobek ATR(14): nezávisí na roce a ceně", loc="left", color=INK, fontweight="bold")
fig.suptitle("Kam cena od open během RTH dojde: podklad pro velikost TP a SL",
             x=0.125, ha="left", color=INK, fontsize=13, fontweight="bold", y=1.0)
fig.savefig(os.path.join(OUT, "dosah_od_open.png"), dpi=150, bbox_inches="tight", facecolor=SURF)
plt.close(fig)

# ---------- 3) měsíční průměry ----------
rows = []
for per, grp in d.groupby(d.index.to_period("M")):
    r = {"mesic": str(per), "dni": len(grp)}
    for k, _ in METRICS:
        x = grp[k]; m = x.mean()
        r[f"{k}_prumer"] = m; r[f"{k}_median"] = x.median()
        r[f"{k}_nad_dni"] = int((x > m).sum()); r[f"{k}_nad_prumer"] = x[x > m].mean()
        r[f"{k}_pod_dni"] = int((x <= m).sum()); r[f"{k}_pod_prumer"] = x[x <= m].mean()
    rows.append(r)
M = pd.DataFrame(rows)
M.round(2).to_csv(os.path.join(OUT, "mesicne.csv"), index=False)
dates = pd.PeriodIndex(M.mesic, freq="M").to_timestamp() + pd.Timedelta(days=14)

fig, axes = plt.subplots(3, 1, figsize=(14, 12), sharex=True, gridspec_kw={"hspace": 0.28})
fig.patch.set_facecolor(SURF)
for ax, (k, name) in zip(axes, METRICS):
    style(ax); gm = d[k].mean()
    ax.fill_between(dates, M[f"{k}_pod_prumer"], M[f"{k}_nad_prumer"], color=LIGHT, alpha=0.25, lw=0)
    ax.plot(dates, M[f"{k}_nad_prumer"], color=DARK, lw=1.3, label="průměr dní NAD měsíčním průměrem")
    ax.plot(dates, M[f"{k}_prumer"], color=MID, lw=2.2, label="měsíční průměr")
    ax.plot(dates, M[f"{k}_pod_prumer"], color=LIGHT, lw=1.3, label="průměr dní POD měsíčním průměrem")
    ax.axhline(gm, color=MUTED, lw=1.2, ls="--", label=f"průměr celých 10 let ({fmt(gm)} b.)")
    mx = M[f"{k}_prumer"].idxmax()
    ax.annotate(f"měsíční průměr max {M.mesic[mx]}: {fmt(M[f'{k}_prumer'][mx])} b.",
                (dates[mx], M[f"{k}_prumer"][mx]), xytext=(-12, 0), ha="right", va="center",
                textcoords="offset points", fontsize=8.5, color=SEC,
                bbox=dict(boxstyle="round,pad=0.2", fc=SURF, ec="none"))
    ax.set_title(name, loc="left", color=INK, fontweight="bold")
    ax.set_ylabel("Body", color=SEC); ax.set_ylim(0, None)
axes[0].legend(frameon=False, labelcolor=SEC, loc="upper left", ncol=2, fontsize=9)
axes[-1].xaxis.set_major_locator(mdates.YearLocator(1)); axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
fig.suptitle("Měsíční průměry ES RTH: průměrný den, dny nad a pod průměrem daného měsíce",
             x=0.125, ha="left", color=INK, fontsize=13, fontweight="bold", y=0.93)
fig.savefig(os.path.join(OUT, "mesicni_prumery.png"), dpi=150, bbox_inches="tight", facecolor=SURF)
plt.close(fig)

# ---------- tabulky ----------
c = lambda v: fmt(v) if pd.notna(v) else "–"
L = ["# Měsíční průměry ES RTH (09:30–16:00 ET), body\n",
     "Pro každý měsíc: průměr všech dní, počet a průměr dní nad měsíčním průměrem a pod ním. "
     "Grafy: `mesicni_prumery.png`, `rozlozeni_vs_prumer.png`, `dosah_od_open.png`. Data: `mesicne.csv`.\n"]
for k, name in METRICS:
    L += [f"\n## {name}\n", "| Měsíc | Dní | Průměr | Medián | Nad: dní | Nad: průměr | Pod: dní | Pod: průměr |",
          "|---|---|---|---|---|---|---|---|"]
    for _, r in M.iterrows():
        L.append(f"| {r.mesic} | {r.dni} | **{c(r[k+'_prumer'])}** | {c(r[k+'_median'])} | {r[k+'_nad_dni']} | "
                 f"{c(r[k+'_nad_prumer'])} | {r[k+'_pod_dni']} | {c(r[k+'_pod_prumer'])} |")
# pravděpodobnosti do přehledu
L += ["\n## Kam cena od open dojde (celé období)\n", "| X | nahoru ≥ X | dolů ≥ X |", "|---|---|---|"]
for q in (5, 10, 15, 20, 25, 30, 40, 50, 60, 80):
    L.append(f"| {q} b. | {(d.ho >= q).mean()*100:.0f} % | {(d.ol >= q).mean()*100:.0f} % |")
da = d.dropna(subset=["atr"])
L += ["\n| X (× ATR14) | nahoru ≥ X | dolů ≥ X |", "|---|---|---|"]
for q in (0.1, 0.25, 0.5, 0.75, 1.0, 1.5):
    L.append(f"| {fmt(q) if q != 0.25 and q != 0.75 else str(q).replace('.', ',')} | "
             f"{(da.ho/da.atr >= q).mean()*100:.0f} % | {(da.ol/da.atr >= q).mean()*100:.0f} % |")
open(os.path.join(OUT, "MESICNE.md"), "w").write("\n".join(L) + "\n")

yr = d.groupby(d.index.year)[["rng", "ol", "ho"]].mean().round(1)
print(yr); print(L[-14:])
