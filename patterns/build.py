"""Denní vlastnosti ES + výsledek 64 jednoduchých LONG šablon pro každý den.
Šablona = vstup (open / open−x·ATR limit / open+x·ATR stop) × SL (k·ATR) × RRR × výstup (16:00 / drží max 10 dní).
Výsledek v R po nákladech 0,5 b. Data: back-adjustované volume bary (24 h), čas ET."""
import sys, os, itertools
import numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "open_fade"))
from open_fade import load_bars
DATA = sys.argv[1]; OUT = "reports/patterns"; os.makedirs(OUT, exist_ok=True)
COST = 0.5
df = load_bars(DATA)
O, H, L, C = (df[k].values for k in ("open", "high", "low", "close")); TS = df.index; N = len(df)
tm = np.array(TS.time); t0, t_last, t_end = pd.Timestamp("09:30").time(), pd.Timestamp("15:59").time(), pd.Timestamp("16:00").time()
rth_idx = np.flatnonzero([(x >= t0) and (x < t_end) for x in tm])
rows = []
for d, grp in pd.Series(rth_idx, index=TS.normalize()[rth_idx]).groupby(level=0):
    ii = grp.values
    if TS[ii[-1]].time() < pd.Timestamp("15:45").time(): continue
    a, b = ii[0], ii[-1]; last_in = ii[np.flatnonzero(tm[ii] <= t_last)[-1]]
    rows.append(dict(date=d, a=a, b=b, last_in=last_in, o=O[a], h=H[a:b+1].max(), l=L[a:b+1].min(), c=C[b]))
D = pd.DataFrame(rows).set_index("date")
# overnight (od předchozího RTH close do 09:30)
prev_b = D.b.shift(1)
D["on_h"] = [H[int(p)+1:a].max() if pd.notna(p) and a > p + 1 else np.nan for p, a in zip(prev_b, D.a)]
D["on_l"] = [L[int(p)+1:a].min() if pd.notna(p) and a > p + 1 else np.nan for p, a in zip(prev_b, D.a)]
D["rng"] = D.h - D.l
D["atr"] = D.rng.rolling(14).mean().shift(1)
pc, ph, pl, po = D.c.shift(1), D.h.shift(1), D.l.shift(1), D.o.shift(1)
F = pd.DataFrame(index=D.index)                       # vlastnosti známé PŘED/NA open dne
gap = (D.o - pc) / D.atr
F["gap nahoru > 0,2 ATR"] = gap > 0.2
F["gap dolů < −0,2 ATR"] = gap < -0.2
F["bez gapu (±0,2 ATR)"] = gap.abs() <= 0.2
F["včera růst (C>O)"] = pc > po
F["včera pokles (C<O)"] = pc < po
cc = D.c.diff()
F["včera close-close < −0,5 ATR"] = (cc / D.atr.shift(1)).shift(1) < -0.5
dn = (cc < 0).astype(int); streak = dn.groupby((dn == 0).cumsum()).cumsum()
F["2+ dny poklesu v řadě"] = streak.shift(1) >= 2
F["3+ dny poklesu v řadě"] = streak.shift(1) >= 3
clv = (pc - pl) / (ph - pl)
F["včera close v dolních 25 % rozpětí"] = clv < 0.25
F["včera close v horních 25 % rozpětí"] = clv > 0.75
F["včera inside day"] = (D.h.shift(1) < D.h.shift(2)) & (D.l.shift(1) > D.l.shift(2))
F["včera NR7"] = D.rng.shift(1) <= D.rng.rolling(7).min().shift(1)
F["včera široký den > 1,5 ATR"] = D.rng.shift(1) > 1.5 * D.atr.shift(1)
onr = (D.on_h - D.on_l) / D.atr
F["overnight rozpětí < 0,3 ATR"] = onr < 0.3
F["overnight rozpětí > 0,6 ATR"] = onr > 0.6
F["open pod overnight low+25 %"] = (D.o - D.on_l) / (D.on_h - D.on_l) < 0.25
F["open nad overnight 75 %"] = (D.o - D.on_l) / (D.on_h - D.on_l) > 0.75
F["open pod včerejším low"] = D.o < pl
F["open nad včerejším high"] = D.o > ph
for i, n in enumerate(["pondělí", "úterý", "středa", "čtvrtek", "pátek"]): F[n] = D.index.dayofweek == i
ym = D.index.to_period("M"); rk = D.groupby(ym).cumcount(); rrk = D.groupby(ym).cumcount(ascending=False)
F["přelom měsíce (poslední + 3 první dny)"] = ((rrk == 0) | (rk <= 2)).values
hi20 = D.c.rolling(20).max().shift(1)
F["včera close = 20denní maximum"] = pc >= hi20
F["včera close > 3 % pod 20d max"] = pc < hi20 * 0.97
atr_rank = D.atr / D.atr.rolling(250, min_periods=60).median()
F["nízká volatilita (ATR < 0,8× medián roku)"] = atr_rank < 0.8
F["vysoká volatilita (ATR > 1,25× medián roku)"] = atr_rank > 1.25
wk = D.c.resample("W-FRI").last().pct_change().shift(1).reindex(D.index, method="ffill")
F["minulý týden pokles"] = wk < 0
F["VŠECHNY DNY"] = True
F = F.fillna(False).astype(bool)

def find_exit(i, entry, stop, tgt, tp_entry, end):
    if L[i] <= stop: return i, stop
    if tp_entry and H[i] >= tgt: return i, tgt
    j = i + 1
    while j <= end:
        k = min(end + 1, j + 20000); o, h, l = O[j:k], H[j:k], L[j:k]
        hit = (o <= stop) | (o >= tgt) | (l <= stop) | (h >= tgt)
        if hit.any():
            m = int(np.argmax(hit))
            if o[m] <= stop or o[m] >= tgt: return j + m, o[m]
            return j + m, (stop if l[m] <= stop else tgt)
        j = k
    return end, C[end]
ENTRIES = {"open": 0.0, "open−0,25ATR": -0.25, "open−0,5ATR": -0.5, "open+0,25ATR": 0.25}
SLS = [0.25, 0.5]; RRRS = [1.0, 1.5, 2.0, 3.0]; EXITS = ["16:00", "drží≤10d"]
tmpl = list(itertools.product(ENTRIES, SLS, RRRS, EXITS))
Rm = np.full((len(D), len(tmpl)), np.nan)
bvals = D.b.values
for di, (d, r) in enumerate(D.iterrows()):
    atr = r.atr
    if not np.isfinite(atr): continue
    a, b, li = int(r.a), int(r.b), int(r.last_in)
    end_hold = int(bvals[min(di + 10, len(D) - 1)])
    for ti, (en, sl_k, rr, ex) in enumerate(tmpl):
        off = ENTRIES[en] * atr
        if off == 0:
            i, e, tpe = a, O[a], True
        elif off < 0:
            lvl = O[a] + off; seg = L[a:li + 1] <= lvl
            if not seg.any(): continue
            i = a + int(np.argmax(seg)); e, tpe = min(lvl, O[i]), False
        else:
            lvl = O[a] + off; seg = H[a:li + 1] >= lvl
            if not seg.any(): continue
            i = a + int(np.argmax(seg)); e, tpe = max(lvl, O[i]), True
        sl = sl_k * atr; j, px = find_exit(i, e, e - sl, e + rr * sl, tpe, b if ex == "16:00" else end_hold)
        Rm[di, ti] = (px - e - COST) / sl
    if di % 500 == 0: print("den", di, flush=True)
names = [f"{en} | SL {sl}ATR | RRR {rr:g}:1 | {ex}" for en, sl, rr, ex in tmpl]
R = pd.DataFrame(Rm, index=D.index, columns=names)
R.to_pickle(f"{OUT}/sablony_R.pkl"); F.to_pickle(f"{OUT}/vlastnosti.pkl"); D.to_pickle(f"{OUT}/dny.pkl")
print("hotovo", R.shape, F.shape)
