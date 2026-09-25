"""Test navržené studie „Lukacino Buy Weakness“ na volume barech ES (Excel, 07/2016–07/2026).

Logika přesně jako v navržené Sierra studii:
* Rozhodnutí v 15:58 ET: „close“ = close posledního baru, který začal před 15:58.
* Denní RTH market profile (09:30–15:58) z volume barů: objem baru rozložený rovnoměrně
  na ticky mezi jeho low a high, POC, value area 70 % (VAH/VAL).
* VAL swing: close < VAL → long na close. Výstup: první rozhodnutí s close > POC dne vstupu,
  nejpozději po Max Hold dnech.
* RSI(2): RSI(2, Wilder) < práh a close > MA200 → long. Výstup: close > MA5, nejpozději Max Hold.
* Katastrofický stop (volitelně): vstup − k × ATR(14 dní RTH rozpětí), hlídaný na všech barech
  včetně noci, gap přes stop = fill na open baru.
* Max. 1 pozice. „Obě“: první signál vstoupí, výstup podle strategie, která vstoupila.
* Náklady 0,5 b. na obchod (1 ES = $50/bod).

python analysis/buy_weakness/backtest.py <bary .pkl/.xlsx> [výstupní složka]
"""
import sys, os
import numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "open_fade"))
from open_fade import load_bars

TICK, COST, PV = 0.25, 0.5, 50.0
OUT = sys.argv[2] if len(sys.argv) > 2 else "reports/buy_weakness"
os.makedirs(OUT, exist_ok=True)

# ---------------- denní data z volume barů ----------------
df = pd.read_pickle(sys.argv[1]) if sys.argv[1].endswith(".pkl") else load_bars(sys.argv[1])
TS = df.index; O, H, L, C, V = (df[k].values for k in ("open", "high", "low", "close", "vol"))
sec = TS.hour * 3600 + TS.minute * 60 + TS.second
date = TS.normalize()
T0, TEND = 9 * 3600 + 1800, 16 * 3600
TDEC = int(os.environ.get("TDEC", 15 * 3600 + 58 * 60))   # čas rozhodnutí (s od půlnoci)

def profile(lo_, hi_, v_):
    lo = int(np.floor(lo_.min() / TICK)); hi = int(np.ceil(hi_.max() / TICK)); n = hi - lo + 1
    vp = np.zeros(n)
    for l, h, v in zip(lo_, hi_, v_):
        a = int(np.floor(l / TICK)) - lo; b = int(np.ceil(h / TICK)) - lo; vp[a:b + 1] += v / (b - a + 1)
    poc = int(vp.argmax()); tot = vp.sum(); inc = vp[poc]; a = b = poc
    while inc < 0.7 * tot:
        up = vp[b + 1] if b + 1 < n else -1; dn = vp[a - 1] if a > 0 else -1
        if up >= dn: b += 1; inc += up
        else: a -= 1; inc += dn
    return (lo + poc) * TICK, (lo + b) * TICK, (lo + a) * TICK

rows = []
for d, idx in pd.Series(np.arange(len(df)), index=date).groupby(level=0):
    ii = idx.values
    s = sec[ii]
    rth = ii[(s >= T0) & (s < TDEC)]
    if len(rth) < 20 or sec[ii][(s < TEND)].max() < 15 * 3600 + 45 * 60:
        continue
    poc, vah, val = profile(L[rth], H[rth], V[rth])
    rows.append(dict(d=d, i_dec=rth[-1], c=C[rth[-1]], h=H[rth].max(), l=L[rth].min(), poc=poc, vah=vah, val=val))
D = pd.DataFrame(rows).set_index("d")
c = D.c.values
D["atr"] = (D.h - D.l).rolling(14).mean().shift(1)
dlt = np.diff(c, prepend=np.nan)
up, dn = np.clip(dlt, 0, None), np.clip(-dlt, 0, None)
au = pd.Series(up).ewm(alpha=1 / 2, adjust=False).mean().values
ad = pd.Series(dn).ewm(alpha=1 / 2, adjust=False).mean().values
D["rsi2"] = 100 - 100 / (1 + au / np.where(ad == 0, 1e-9, ad))
D["ma200"] = D.c.rolling(200).mean(); D["ma5"] = D.c.rolling(5).mean()
D.to_pickle(os.path.join(OUT, "_daily.pkl"))
print(f"dní {len(D)} ({D.index[0]:%Y-%m-%d} – {D.index[-1]:%Y-%m-%d})")

N = len(D); I_DEC = D.i_dec.values

def sig_val(k, above_ma200=False):
    r = D.iloc[k]
    return r.c < r.val and (not above_ma200 or (pd.notna(r.ma200) and r.c > r.ma200))

def sig_rsi(k, thr=10):
    r = D.iloc[k]
    return pd.notna(r.ma200) and r.rsi2 < thr and r.c > r.ma200

def run(strategy="val", max_hold=10, stop_k=0.0, val_ma200=False, rsi_thr=10, add_on=False):
    """strategy: val / rsi / both. Vrací DataFrame obchodů."""
    trades = []; k = 200 if strategy != "val" else 15
    while k < N - 1:
        which = None
        if strategy in ("val", "both") and sig_val(k, val_ma200): which = "val"
        elif strategy in ("rsi", "both") and sig_rsi(k, rsi_thr): which = "rsi"
        if which is None or pd.isna(D.atr.iloc[k]): k += 1; continue
        e = c[k]; poc0 = D.poc.iloc[k]; stop = e - stop_k * D.atr.iloc[k] if stop_k > 0 else -np.inf
        qty = 1; adds = []
        exit_px = None; reason = "time"; j = k
        for j in range(k + 1, min(k + max_hold, N - 1) + 1):
            # stop na všech barech od vstupu do rozhodnutí dne j
            if stop_k > 0:
                seg = slice(I_DEC[j - 1] + 1, I_DEC[j] + 1)
                lows = L[seg]; hit = np.flatnonzero(lows <= stop)
                if len(hit):
                    b = seg.start + hit[0]; exit_px = min(O[b], stop); reason = "stop"; break
            cj = c[j]
            if which == "val" and cj > poc0: exit_px = cj; reason = "poc"; break
            if which == "rsi" and cj > D.ma5.iloc[j]: exit_px = cj; reason = "ma5"; break
            if add_on and which == "val" and qty == 1 and sig_val(j, val_ma200):
                adds.append(cj); qty = 2
        if exit_px is None: exit_px = c[j]
        pnl = (exit_px - e - COST) + sum(exit_px - a - COST for a in adds)
        trades.append(dict(entry_d=D.index[k], exit_d=D.index[j], strat=which, entry=e, exit=exit_px,
                           qty=qty, days=j - k, reason=reason, pts=pnl, risk_pts=max(stop_k, 2.5) * D.atr.iloc[k]))
        k = j  # nový signál se hledá už v den výstupu (po uzavření pozice), stejně jako ve studii
    return pd.DataFrame(trades)

def tstat(p): return p.mean() / p.std(ddof=1) * np.sqrt(len(p)) if len(p) > 2 else np.nan

def random_null(tr, n_sim=2000, seed=0):
    """Náhodné dny vstupu (stejný počet, stejné délky držení), long close→close + náklady."""
    rng = np.random.default_rng(seed); hold = tr.days.values; lo = 15
    res = np.empty(n_sim)
    for s in range(n_sim):
        ks = rng.integers(lo, N - hold.max() - 1, len(hold))
        res[s] = (c[ks + hold] - c[ks] - COST).mean()
    return res

def summary(tr, name):
    p = tr.pts.values; eq = np.cumsum(p)
    yrs = tr.groupby(tr.entry_d.dt.year).pts.sum()
    null = random_null(tr)
    is_ = tr[tr.entry_d < "2022-01-01"].pts; oos = tr[tr.entry_d >= "2022-01-01"].pts
    new = tr[tr.entry_d < ("2018-07-09" if "VAL" in name else "2019-05-01")].pts
    return dict(varianta=name, obchodu=len(p), win=(p > 0).mean() * 100, b_obchod=p.mean(), t=tstat(p),
                usd=p.sum() * PV, maxdd_usd=(eq - np.maximum.accumulate(eq)).min() * PV,
                nejhorsi_b=p.min(), drzeni_dni=tr.days.mean(), kladne_roky=f"{(yrs > 0).sum()}/{len(yrs)}",
                nahoda_b=null.mean(), p_nahoda=(null >= p.mean()).mean(),
                is_2016_21_b=is_.mean(), is_t=tstat(is_.values), oos_2022_26_b=oos.mean(), oos_t=tstat(oos.values),
                nova_data_n=len(new), nova_data_b=new.mean() if len(new) else np.nan)

VARS = [
    ("VAL swing (výzkum: bez stopu, max 10 dní)", dict(strategy="val")),
    ("VAL swing + stop 3×ATR", dict(strategy="val", stop_k=3.0)),
    ("VAL swing + stop 2,5×ATR", dict(strategy="val", stop_k=2.5)),
    ("VAL swing jen nad MA200", dict(strategy="val", val_ma200=True)),
    ("VAL swing max 5 dní", dict(strategy="val", max_hold=5)),
    ("VAL swing + add-on", dict(strategy="val", add_on=True)),
    ("RSI(2)<10 nad MA200 (výzkum)", dict(strategy="rsi")),
    ("RSI(2)<10 + stop 3×ATR", dict(strategy="rsi", stop_k=3.0)),
    ("RSI(2)<5 nad MA200", dict(strategy="rsi", rsi_thr=5)),
    ("RSI(2)<20 nad MA200", dict(strategy="rsi", rsi_thr=20)),
    ("Obě (1 pozice, první signál)", dict(strategy="both")),
    ("Obě + stop 3×ATR", dict(strategy="both", stop_k=3.0)),
]
res, all_tr = [], {}
for name, kw in VARS:
    tr = run(**kw); all_tr[name] = tr
    res.append(summary(tr, name)); print(name, len(tr), round(tr.pts.mean(), 2), round(tstat(tr.pts.values), 2), flush=True)
R = pd.DataFrame(res); R.round(3).to_csv(os.path.join(OUT, "varianty.csv"), index=False)
pd.to_pickle(all_tr, os.path.join(OUT, "_trades.pkl"))
pd.set_option("display.width", 250)
print(R.round(2).to_string(index=False))
