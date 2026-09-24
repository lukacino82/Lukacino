"""Nulová hypotéza pro variantu bez výstupu v 16:00: long v náhodném čase RTH
(bez podmínky open±X), stejný SL 20 / TP 40 nebo 60, drží do TP/SL, max. 1 pozice."""
import sys, os, importlib.util
import numpy as np, pandas as pd
spec = importlib.util.spec_from_file_location("h", os.path.join(os.path.dirname(__file__), "long_sl20_hold.py"))
sys.argv = [sys.argv[0], sys.argv[1], "/tmp/_ignore"]
# načti jen pomocné části skriptu (data + find_exit) bez spuštění celé mřížky
src = open(os.path.join(os.path.dirname(__file__), "long_sl20_hold.py")).read().split("rows, trades = [], []")[0]
ns = {"__file__": os.path.join(os.path.dirname(__file__), "long_sl20_hold.py")}; exec(src, ns)
days, find_exit, TS, O, tm, t_last = ns["days"], ns["find_exit"], ns["TS"], ns["O"], ns["tm"], ns["t_last"]
COST = 0.5
for tp in (40.0, 60.0):
    res = []
    for seed in range(30):
        rng = np.random.default_rng(seed); busy = -1; pts = []
        for d, a, b in days:
            if a <= busy: continue
            cand = [i for i in range(a, b + 1) if tm[i] <= t_last]
            i = cand[rng.integers(len(cand))]; e = O[i]
            j, px, r = find_exit(i, e, e - 20.0, e + tp, True); busy = j; pts.append(px - e - COST)
        p = np.array(pts); res.append((len(p), p.mean(), p.sum() * 50))
    r = np.array(res)
    print(f"TP {tp:.0f}/SL 20 náhodný long: obchodů ~{r[:,0].mean():.0f}, b./obchod {r[:,1].mean():.2f} "
          f"(5–95 %: {np.quantile(r[:,1],.05):.2f} až {np.quantile(r[:,1],.95):.2f}), $ celkem průměr {r[:,2].mean():,.0f} "
          f"(5–95 %: {np.quantile(r[:,2],.05):,.0f} až {np.quantile(r[:,2],.95):,.0f})")
