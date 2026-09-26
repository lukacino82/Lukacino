"""
Massive grid: every SETUP x REGIME x EXIT x DIRECTION is backtested on the full history.
Only statistics are stored (results/grid.parquet); finalists are re-run in detail by sieve.py.

usage: python grid.py [--cost 0.5] [--procs 4]
"""
from __future__ import annotations

import argparse
import os
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

import systems as S
from lab import WF_END, WF_PERIODS, Lab

RES = Path(__file__).resolve().parent / "results"
_G = {}


def _init(cost, wf=False):
    lab = Lab(end=WF_END, periods=WF_PERIODS) if wf else Lab()
    _G["lab"] = lab
    _G["setups"] = S.setups(lab.d)
    _G["exits"] = S.exits(lab.d)
    _G["reg"] = S.regimes(lab.d)
    _G["cost"] = cost


def _job(args):
    si, regime, side = args
    lab, setup, exits = _G["lab"], _G["setups"][si], _G["exits"]
    rows = []
    mask = _G["reg"][regime]
    for ex in exits:
        cfg = S.build_cfg(lab.d, setup, ex, side, mask, _G["cost"])
        if cfg is None or cfg["side"].sum() == 0:
            continue
        pnl, pos, tr = lab.run(cfg)
        st = lab.stats(pnl, pos, tr)
        st.update(setup=setup[0], regime=regime, side=side, exit=ex[0])
        rows.append(st)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cost", type=float, default=0.5)
    ap.add_argument("--procs", type=int, default=os.cpu_count())
    ap.add_argument("--out", default=None)
    ap.add_argument("--wf", action="store_true", help="walk-forward: only data up to WF_END")
    a = ap.parse_args()
    RES.mkdir(exist_ok=True)
    a.out = a.out or ("grid_wf.parquet" if a.wf else "grid.parquet")
    _init(a.cost, a.wf)
    jobs = []
    for si, st in enumerate(_G["setups"]):
        for r in S.LONG_REGIMES:
            jobs.append((si, r, 1))
        if st[2] is not None:
            for r in S.SHORT_REGIMES:
                jobs.append((si, r, -1))
    print(f"{len(jobs)} setup x regime x side jobs, {len(_G['exits'])} exits each")
    t = time.time()
    rows = []
    with Pool(a.procs, initializer=_init, initargs=(a.cost, a.wf)) as p:
        for i, r in enumerate(p.imap_unordered(_job, jobs, chunksize=4)):
            rows.extend(r)
            if i % 200 == 0:
                print(f"{i}/{len(jobs)} jobs, {len(rows)} systems, {time.time() - t:.0f}s", flush=True)
    df = pd.DataFrame(rows)
    df.to_parquet(RES / a.out)
    print(f"done: {len(df)} systems in {time.time() - t:.0f}s -> {RES / a.out}")


if __name__ == "__main__":
    main()
