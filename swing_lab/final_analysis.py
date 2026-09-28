"""
Final answer to "which systems beat buy & hold, alone and in a group", with equity curves.

Fair comparison rule: a swing system that is flat most of the time can never beat B&H on total
return with one contract, and can always beat it by adding leverage. So every book is also shown
VOLATILITY-MATCHED: scaled so its annualised volatility equals B&H, which makes total return
directly comparable at equal risk.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from ensemble import EnsembleBook
from lab import Lab
from overlay import pct_series, stats
from sieve import RES
from winners import family_key

MIN_TRADES = 40
CAP = 250


def vol_match(r, target_vol):
    k = target_vol / (r.std() * np.sqrt(252))
    return r * k, k


def main():
    lab = Lab()
    s0 = lab.start_i
    close = lab.d.close.values
    idx = lab.idx[s0:]
    bh = pct_series(lab.bh, close)[s0:]
    tgt = bh.std() * np.sqrt(252)
    bh_st = stats(bh, bh)
    g = pd.read_parquet(RES / "grid.parquet")
    g = g[(~g.exit.str.contains(r"\d+pt_")) & (g.trades >= MIN_TRADES)].copy()
    g["fam"] = g.setup.map(family_key)
    eb = EnsembleBook(lab)

    fam_r, fam_meta = {}, {}
    for (fam, side), q in g.groupby(["fam", "side"]):
        qs = q.sample(min(CAP, len(q)), random_state=7)
        p, pos = eb.family_pnl(qs[["setup", "regime", "side", "exit"]])
        r = pct_series(p, close)[s0:]
        if r.std() == 0:
            continue
        fam_r[(fam, side)] = r
        fam_meta[(fam, side)] = dict(variants=len(q), exposure=float((pos[s0:] != 0).mean()))

    rows = []
    for k, r in fam_r.items():
        st = stats(r, bh)
        rv, mult = vol_match(r, tgt)
        sv = stats(rv, bh)
        st.update(family=k[0], side=k[1], **fam_meta[k],
                  vm_cagr=sv["cagr"], vm_maxdd=sv["maxdd"], vm_mult=round(mult, 1))
        st["beats_bh"] = (st["sharpe"] > bh_st["sharpe"]) and (st["mar"] > bh_st["mar"])
        rows.append(st)
    fam_df = pd.DataFrame(rows).sort_values("alpha_t", ascending=False)
    fam_df.to_csv(RES / "final_families.csv", index=False)

    # ---- groups. "Blueprint roles" uses the prefix map only (no performance selection) ----
    role_map = {"R1 shallow pullback": ("A01", "C01", "C04", "D01"),
                "R2 deep correction": ("B01", "B02", "B03", "B04", "A03", "A04"),
                "R3 auction rejection": ("E01", "E02", "E03", "E04", "E05"),
                "R4 delta exhaustion": ("F01", "F02", "F03", "F05", "F06", "F09"),
                "R5 deceleration/failure": ("A05", "A06", "A07", "A08", "A09", "A10", "A12"),
                "R6 confluence": ("G01", "G02", "G03")}
    roles = {}
    for name, pref in role_map.items():
        sub = [r for (f, s), r in fam_r.items() if s > 0 and f in pref]
        if sub:
            roles[name] = np.mean(sub, axis=0)
    blueprint = np.mean(list(roles.values()), axis=0)
    winners_sel = [k for k in fam_r if k[1] > 0 and fam_df.set_index(["family", "side"]).loc[k, "beats_bh"]]
    grp_sel = np.mean([fam_r[k] for k in winners_sel], axis=0)

    books = {"Buy & Hold": bh, "Blueprint roles (no selection)": blueprint,
             f"Winners group ({len(winners_sel)} families, selected)": grp_sel}
    for nm, r in list(roles.items()):
        books[nm] = r
    out, curves = {}, {"dates": [str(x.date()) for x in idx]}
    for k, r in books.items():
        st = stats(r, bh)
        rv, mult = vol_match(r, tgt)
        sv = stats(rv, bh)
        st.update(vm_cagr=sv["cagr"], vm_maxdd=sv["maxdd"], vm_sharpe=sv["sharpe"], vm_mult=round(mult, 1))
        out[k] = st
        curves[k] = (np.cumprod(1 + r) - 1) * 100
    # core + overlay at matched total volatility
    for w in (1, 2, 3):
        r = bh + w * blueprint
        st = stats(r, bh)
        rv, _ = vol_match(r, tgt)
        st.update(vm_cagr=stats(rv, bh)["cagr"], vm_maxdd=stats(rv, bh)["maxdd"], vm_sharpe=stats(rv, bh)["sharpe"])
        out[f"Core + {w}x blueprint overlay"] = st
        curves[f"Core + {w}x blueprint overlay"] = (np.cumprod(1 + r) - 1) * 100
    bdf = pd.DataFrame(out).T
    bdf.to_csv(RES / "final_books.csv")

    wk = pd.Series(np.arange(len(idx)), index=idx).groupby(idx.to_period("W")).last().values
    top8 = [f"{f}" for f, s in fam_df[fam_df.beats_bh & (fam_df.side > 0)].head(8)[["family", "side"]].itertuples(index=False)]
    for f in top8:
        curves[f"FAM {f}"] = (np.cumprod(1 + fam_r[(f, 1)]) - 1) * 100
    cur = {k: ([round(float(x), 3) for x in np.asarray(v)[wk]] if k != "dates" else [v[i] for i in wk])
           for k, v in curves.items()}
    json.dump(cur, open(RES / "final_curves.json", "w"))

    yrs = idx.year.values
    yr = pd.DataFrame({k: pd.Series(v).groupby(yrs).sum() * 100 for k, v in
                       [("Buy & Hold", bh), ("Blueprint overlay", blueprint), ("Core+2x", bh + 2 * blueprint)]}).round(1)
    yr.to_csv(RES / "final_years.csv")

    pd.set_option("display.width", 260)
    print("B&H:", bh_st)
    cols = ["family", "side", "variants", "exposure", "cagr", "maxdd", "sharpe", "mar", "beta", "alpha_ann",
            "alpha_t", "vm_cagr", "vm_maxdd", "vm_mult", "beats_bh"]
    w = fam_df[fam_df.beats_bh]
    print(f"\n=== FAMILIES THAT BEAT B&H ALONE (Sharpe AND MAR): {len(w)} of {len(fam_df)} ===")
    print(w[cols].to_string(index=False))
    print("\n=== GROUPS ===")
    print(bdf.to_string())
    print("\n=== YEARLY % ===")
    print(yr.to_string())


if __name__ == "__main__":
    main()
