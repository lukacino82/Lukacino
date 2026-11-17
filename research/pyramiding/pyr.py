"""Pyramiding (přikupování k vítězi s klesajícím rizikem) – test na ES 1min 2008-2026.
Postup z videa: 1. vstup = 1R, přidání jen po příznivém pohybu, každé přidání menší (0.5R, 0.25R, ..),
celá pozice se po přidání posune stopem na předchozí úroveň -> riziko klesá, velikost roste.
Testujeme: (1) zda pyramiding mění očekávanou hodnotu (martingale argument), (2) zda vstupy z videa
(opening range break, 'fashionably late' EMA9/VWAP) mají edge, (3) tvar rozdělení výsledků.
Veškerý výsledek v R (R = počáteční riziko = vzdálenost stopu), náklad 0.5 b. na kontrakt a obrat.
"""
import sys, numpy as np, pandas as pd
from numba import njit
sys.path.insert(0, "/home/user/Lukacino/research/mega")
import daily as D
COST = 0.5

@njit(cache=True)
def manage(H, L, C, i0, end, s, entry, r, mode, a, nadd, tgt):
    # souřadnice 'příznivě nahoru': p = s*cena
    P0 = s * entry; stp = P0 - r; size = 1.0; avg = P0; traded = 1.0; k = 0
    nxt = 1
    for j in range(i0 + 1, end + 1):
        hi = H[j] if s == 1 else -L[j]
        lo = L[j] if s == 1 else -H[j]
        if lo <= stp:
            return size * (stp - avg) / r, traded, k, 0
        if mode == 1 and hi >= P0 + tgt * r:
            return size * (P0 + tgt * r - avg) / r, traded, k, 1
        if mode == 2 or mode == 3:
            while k < nadd and hi >= P0 + (k + 1) * a * r:
                lvl = P0 + (k + 1) * a * r
                if mode == 2:
                    f = max(0.5 ** (k + 1), 0.1); sz = f / a
                else:
                    sz = 1.0
                avg = (avg * size + lvl * sz) / (size + sz); size += sz; traded += sz
                stp = P0 + k * a * r          # celá pozice na předchozí úroveň (k=0 -> breakeven)
                k += 1
        if mode == 4:
            while k < 2 and lo <= P0 - (0.4 + 0.3 * k) * r:
                lvl = P0 - (0.4 + 0.3 * k) * r
                avg = (avg * size + lvl) / (size + 1.0); size += 1.0; traded += 1.0; k += 1
    px = s * C[end]
    return size * (px - avg) / r, traded, k, 2

@njit(cache=True)
def run(H, L, C, idx, side, rr, endi, mode, a, nadd, tgt):
    n = len(idx); R = np.zeros(n); T = np.zeros(n); K = np.zeros(n); X = np.zeros(n)
    for q in range(n):
        R[q], T[q], K[q], X[q] = manage(H, L, C, idx[q], endi[q], side[q], C[idx[q]], rr[q], mode, a, nadd, tgt)
    return R, T, K, X

def prep():
    d = D.minute(); t = D.daily_table(d)
    d = d.reset_index(drop=True)
    rth = (d["mod"] >= 570) & (d["mod"] < 960)
    r = d[rth].reset_index(drop=True)
    days = r.gday.to_numpy()
    u, st = np.unique(days, return_index=True)
    en = np.r_[st[1:] - 1, len(r) - 1]
    ti = t.index.to_numpy()
    prev = np.searchsorted(ti, u, side="left") - 1
    atr = np.where(prev >= 0, t.atr.to_numpy()[np.maximum(prev, 0)], np.nan)
    return r, u, st, en, atr

def entries(r, u, st, en, atr, kind, seed=0):
    H = r.High.to_numpy(); L = r.Low.to_numpy(); C = r.Close.to_numpy(); V = r.Volume.to_numpy().astype(float)
    rng = np.random.default_rng(seed); out = []
    tp = (H + L + C) / 3
    for d in range(len(u)):
        a_ = atr[d]
        if not (a_ > 0): continue
        s0, e0 = st[d], en[d]
        if e0 - s0 < 300: continue
        if kind == "random":
            i = s0 + int(rng.integers(30, 270)); out.append((d, i, 0, a_, e0)); continue
        if kind == "orb":
            hi = H[s0:s0 + 30].max(); lo = L[s0:s0 + 30].min()
            for j in range(s0 + 30, e0 - 20):
                if H[j] > hi: out.append((d, j, 1, a_, e0, hi - lo)); break
                if L[j] < lo: out.append((d, j, -1, a_, e0, hi - lo)); break
        if kind == "late":
            cv = np.cumsum(tp[s0:e0 + 1] * V[s0:e0 + 1]); vv = np.cumsum(V[s0:e0 + 1]) + 1e-9
            vw = cv / vv
            ema = np.empty(e0 - s0 + 1); al = 2 / 10; ema[0] = C[s0]
            for q in range(1, len(ema)): ema[q] = al * C[s0 + q] + (1 - al) * ema[q - 1]
            lod = np.minimum.accumulate(L[s0:e0 + 1]); hod = np.maximum.accumulate(H[s0:e0 + 1])
            for q in range(31, len(ema) - 20):
                if ema[q - 1] <= vw[q - 1] and ema[q] > vw[q] and C[s0 + q] > vw[q]:
                    dist = C[s0 + q] - lod[q]
                    if dist >= 0.3 * a_: out.append((d, s0 + q, 1, a_, e0, dist)); break
                if ema[q - 1] >= vw[q - 1] and ema[q] < vw[q] and C[s0 + q] < vw[q]:
                    dist = hod[q] - C[s0 + q]
                    if dist >= 0.3 * a_: out.append((d, s0 + q, -1, a_, e0, dist)); break
    return out

SCH = [("S0 jedna pozice, stop −1R, drží do konce dne", 0, 1, 0, 0), ("S1 stop −1R, cíl +3R", 1, 1, 0, 3.0),
       ("S2 pyramid video (0.5R,0.25R,0.125R, stop na předchozí úroveň)", 2, 1.0, 3, 0), ("S3 pyramid stejné velikosti (přikupování zvětšuje riziko)", 3, 1.0, 3, 0),
       ("S4 pyramid video, krok 2R", 2, 2.0, 3, 0), ("S5 průměrování ztráty (přidání při −0.4R a −0.7R)", 4, 1, 2, 0)]

def tstat(x, wk):
    g = pd.DataFrame({"x": x, "w": wk}).groupby("w").x.agg(["sum", "count"]); n = g["count"].sum(); m = g["sum"].sum() / n
    se = np.sqrt(((g["sum"] - m * g["count"]) ** 2).sum()) / n
    return m, (m / se if se > 0 else np.nan)

def main():
    r, u, st, en, atr = prep()
    H = r.High.to_numpy(); L = r.Low.to_numpy(); C = r.Close.to_numpy()
    rows = []
    for kind in ["random", "orb", "late"]:
        ent = entries(r, u, st, en, atr, kind)
        for rat in ([0.10, 0.20, 0.30] if kind != "late" else [None]):
            idx = np.array([e[1] for e in ent]); day = np.array([e[0] for e in ent]); atrs = np.array([e[3] for e in ent]); endi = np.array([e[4] for e in ent])
            if kind == "random":
                sides = [1, -1]
            elif kind == "orb":
                sides = ["sig", "fade"]
            else:
                sides = ["sig", "fade"]
            for sd in sides:
                if kind == "random": sv = np.full(len(idx), sd)
                else:
                    sg = np.array([e[2] for e in ent]); sv = sg if sd == "sig" else -sg
                if kind == "late":
                    dist = np.array([e[5] for e in ent]); rr = dist / 3.0
                else:
                    rr = rat * atrs
                ok = rr > 0.5
                for nm, mode, a, nadd, tgt in SCH:
                    R, T, K, X = run(H, L, C, idx[ok], sv[ok].astype(np.int64), rr[ok], endi[ok], mode, a, nadd, tgt)
                    net = R - COST * T / rr[ok] - 0  # 1 hrana vstupu + výstup v rámci COST
                    yr = pd.to_datetime(u[day[ok]]).year.to_numpy(); wk = pd.to_datetime(u[day[ok]]).to_period("W").astype(str)
                    for per, lo_, hi_ in [("vše", 2000, 2100), ("08-15", 2008, 2015), ("16-20", 2016, 2020), ("21-26", 2021, 2026)]:
                        mk = (yr >= lo_) & (yr <= hi_)
                        if mk.sum() < 100: continue
                        m, t = tstat(net[mk], wk[mk]); mg = R[mk].mean()
                        rows.append(dict(entry=kind, risk_atr=rat if rat else np.nan, side=str(sd), scheme=nm, period=per, n=int(mk.sum()),
                                         gross_R=mg, net_R=m, t=t, win=(R[mk] > 0).mean(), median=np.median(R[mk]), p95=np.percentile(R[mk], 95), p99=np.percentile(R[mk], 99), minR=R[mk].min(),
                                         sd=R[mk].std(), size=T[mk].mean(), adds=K[mk].mean()))
        print(kind, len(ent), flush=True)
    df = pd.DataFrame(rows); df.to_csv("out/pyr_results.csv", index=False); print(df.shape)

if __name__ == "__main__":
    main()
