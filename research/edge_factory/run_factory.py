"""Run every hypothesis family through the factory and save the result table."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
from data import load
from factory import Factory
from hypotheses import FAMILIES, Ctx

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT, exist_ok=True)

if __name__ == "__main__":
    t = time.time()
    D = load(); F = Factory(D); C = Ctx(D)
    print("setup", round(time.time() - t), "s")
    for fam in FAMILIES:
        n0 = len(F.results); t1 = time.time()
        fam(F, C)
        print(f"{fam.__name__:20s} {len(F.results) - n0:6d} testů  {time.time() - t1:5.0f}s", flush=True)
    R = F.table()
    R.to_csv(os.path.join(OUT, "factory_results.csv"), index=False)
    print("celkem testů", len(R), "| FDR v DISC", int(R.fdr.sum()), "| potvrzeno VAL+TEST", int(R.confirm.sum()), "| obchodovatelné", int(R.tradeable.sum()))
