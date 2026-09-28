"""
Blueprint G05: does a correction overlay add alpha on top of a long S&P core?

The only honest test is  Core + Overlay  minus  Core  at the same capital, costs and risk limit.
Reported per unit of notional (percent), not in points, because ES went from 1400 to 7800 and a
fixed 1-contract overlay silently shrinks over time.

Roles (blueprint "portfolio of roles"): one family cap each, so five variants of the same IBS
signal can never masquerade as five independent bets.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

import systems as S
from ensemble import EnsembleBook
from lab import Lab
from sieve import RES


def pct_series(pnl, close):
    """daily P&L of 1 ES expressed as a return on notional (1 point = 1/price of notional)"""
    prev = np.r_[np.nan, close[:-1]]
    return pnl / prev


def stats(r, bench=None, ann=252):
    r = np.asarray(r, float)
    eq = np.cumprod(1 + r)
    cagr = eq[-1] ** (ann / len(r)) - 1
    dd = (eq / np.maximum.accumulate(eq) - 1).min()
    out = dict(cagr=round(cagr * 100, 2), maxdd=round(dd * 100, 1), vol=round(r.std() * np.sqrt(ann) * 100, 1),
               sharpe=round(r.mean() / r.std() * np.sqrt(ann), 2) if r.std() > 0 else 0.0,
               mar=round(cagr / -dd, 2) if dd < 0 else 0.0)
    if bench is not None:
        b = np.asarray(bench, float)
        beta = np.cov(r, b)[0, 1] / b.var()
        res = r - beta * b
        ir = res.mean() / res.std() * np.sqrt(ann) if res.std() > 0 else 0.0
        out.update(beta=round(beta, 2), alpha_ann=round(res.mean() * ann * 100, 2), alpha_ir=round(ir, 2),
                   alpha_t=round(ir * np.sqrt(len(r) / ann), 2))
    return out


def family_pnl(lab: Lab, g: pd.DataFrame, setups, regime=None, side=1, min_n=1):
    """equal-weight ensemble of every qualifying variant of one family (never a single best parameter)"""
    q = g[g.setup.isin(setups) & (g.side == side)]
    if regime:
        q = q[q.regime.isin(regime)]
    if len(q) < min_n:
        return None, 0
    return EnsembleBook(lab).family_pnl(q[["setup", "regime", "side", "exit"]])[0], len(q)


def main():
    lab = Lab()
    s0 = lab.start_i
    d = lab.d
    close = d.close.values
    g = pd.read_parquet(RES / "grid.parquet")
    g = g[~g.exit.str.contains(r"\d+pt_")]
    # a variant qualifies only if it is profitable after costs in every period and has enough trades
    okv = g[(g.trades >= 40) & (g.disc_avg > 0) & (g.val_avg > 0) & (g.oos_avg > 0) & (g.pf > 1.2)]
    roles = {
        "R1 shallow pullback": [s for s in okv.setup.unique() if s.startswith(("A01_", "C01_", "C04_", "D01_"))],
        "R2 deep correction": [s for s in okv.setup.unique() if s.startswith(("B01_", "B02_", "B03_", "B04_", "A03_", "A04_"))],
        "R3 auction rejection": [s for s in okv.setup.unique() if s.startswith(("E01_", "E02_", "E03_", "E04_", "E05_"))],
        "R4 delta exhaustion": [s for s in okv.setup.unique() if s.startswith(("F01_", "F02_", "F03_", "F05_", "F06_", "F09_"))],
        "R5 deceleration / failure": [s for s in okv.setup.unique() if s.startswith(("A05_", "A06_", "A07_", "A08_", "A09_", "A10_", "A12_"))],
        "R6 confluence engines": [s for s in okv.setup.unique() if s.startswith(("G01_", "G02_", "G03_"))],
        "R7 bear defense": [s for s in okv.setup.unique() if s.startswith("G08_")],
    }
    parts, meta = {}, {}
    for name, ss in roles.items():
        side = -1 if name.startswith("R7") else 1
        p, n = family_pnl(lab, okv, ss, side=side)
        if p is None:
            meta[name] = dict(variants=0)
            continue
        parts[name] = p
        meta[name] = dict(variants=int(n), setups=len(ss))
    core = np.zeros(lab.n)
    core[s0 + 1:] = np.diff(close[s0:])                      # 1 ES buy & hold
    bh = pct_series(lab.bh, close)[s0:]
    overlay = sum(parts.values())
    books = {"Core (B&H 1 ES)": lab.bh}
    for k, v in parts.items():
        books[f"Overlay {k}"] = v
    books["Overlay all roles"] = overlay
    for w in (0.25, 0.5, 1.0):
        books[f"Core + {w:g}x overlay"] = lab.bh + w * overlay
    res = {}
    for k, v in books.items():
        r = pct_series(v, close)[s0:]
        res[k] = stats(r, bh)
        res[k]["variants"] = meta.get(k.replace("Overlay ", ""), {}).get("variants", None)
    out = pd.DataFrame(res).T
    print(out.to_string())
    # the decisive number: Core+Overlay minus Core, tested for significance
    for w in (0.25, 0.5, 1.0):
        diff = pct_series(w * overlay, close)[s0:]
        t = diff.mean() / diff.std() * np.sqrt(len(diff))
        print(f"Overlay {w:g}x alone: ann {diff.mean()*252*100:+.2f} %, t={t:.2f}, "
              f"corr with core {np.corrcoef(diff, bh)[0,1]:+.2f}")
    yrs = d.index.year.values[s0:]
    yr = pd.DataFrame({k: pd.Series(pct_series(v, close)[s0:]).groupby(yrs).sum() * 100 for k, v in books.items()
                       if k.startswith(("Core", "Overlay all"))}).round(1)
    print(yr.to_string())
    json.dump({"stats": res, "meta": meta, "yearly": yr.to_dict()}, open(RES / "overlay.json", "w"), default=float, indent=1)
    np.save(RES / "overlay_pnl.npy", overlay)
    return out


if __name__ == "__main__":
    main()
