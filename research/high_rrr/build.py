"""Build entry events + context and run the outcome scan for EOD and 5-day horizons."""
import os, sys, time, pickle
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "edge_factory"))
import numpy as np, pandas as pd
import data as efd
from engine import load_1m, run_scan
from context import build_context, build_events, horizon_ends

OUTD = "/tmp/claude-0/data/hr_scan.pkl"

if __name__ == "__main__":
    t = time.time()
    D = efd.load(); X = load_1m()
    ctx = build_context(D); print("context", round(time.time() - t), "s", flush=True)
    E = build_events(D, ctx, X); print("events", len(E), round(time.time() - t), "s", flush=True)
    print(E.groupby(["fam", "side"]).size())
    eod, end5, ok = horizon_ends(X, E)
    E = E[ok].reset_index(drop=True); eod, end5 = eod[ok], end5[ok]
    res = {}
    for hz, ends in (("EOD", eod), ("5D", end5)):
        t1 = time.time()
        res[hz] = run_scan(X, E.i1.to_numpy(), ends, E.side.to_numpy())
        print(hz, "scan", round(time.time() - t1), "s", flush=True)
    pickle.dump(dict(E=E, res=res), open(OUTD, "wb"), protocol=4)
