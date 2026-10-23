"""BCL H1 lines (REBEL_POSUN_KONSTANTA 7: cycle = 0.28028 % of price, red anchor 7786.72 from the user's H1 chart)
on 1-min US500Cash-equivalent prices 2018-07 .. 2026-09 (broker-calibrated part only: the 2008-18 reconstruction is
not precise enough for 2-5 point quarter lines). Same protocol as bcl_test.py, horizon 10 trading days, cost 0.6 pt."""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

import bcl_data as BD
from bcl_test import DC, NNULL, OUT, TYPES, run, summary

C_H1, R0_H1, HOR_DAYS = 0.0028028, 7786.72, 10


def main():
    df = BD.load()
    df = df[df.ts >= BD.SWITCH]
    H, L, C, ts = df.H.to_numpy(), df.L.to_numpy(), df.C.to_numpy(), df.ts.values
    hor = HOR_DAYS * 1380
    per = np.where(ts < np.datetime64("2022-07-01"), "2018–22", "2022–26")
    bar, typ, dr, res = run(H, L, C, C_H1, R0_H1, hor)
    real = summary(bar, typ, res, ts)
    realp = {p: summary(bar[per[bar] == p], typ[per[bar] == p], {k: v[per[bar] == p] for k, v in res.items()}, ts)
             for p in ("2018–22", "2022–26")}
    us = np.random.default_rng(29).random(NNULL)
    nulls = []
    for i, u in enumerate(us):
        bb, tt, dd, rr = run(H, L, C, C_H1, R0_H1 * (1 / (1 - C_H1)) ** u, hor)
        nulls.append(summary(bb, tt, rr, ts))
        if i % 20 == 0:
            print("null", i, flush=True)
    keys = list(real.keys())
    NM = np.array([[n[k][0] for k in keys] for n in nulls])
    rows = []
    for i, k in enumerate(keys):
        v, n = real[k]
        rows.append(dict(mrizka="H1", typ=k[0], smer=k[1], TP_cyklu=k[2], SL_cyklu=k[3], n=n, R=v,
                         null_R=np.nanmean(NM[:, i]), p=np.mean(NM[:, i] >= v),
                         **{f"R {p}": realp[p][k][0] for p in realp}))
    S = pd.DataFrame(rows); S["excess"] = S.R - S.null_R
    S.round(4).to_csv(os.path.join(OUT, "bcl_h1_configs.csv"), index=False)
    mu = np.nanmean(NM, axis=0)
    real_best = np.nanmax(S.excess.to_numpy()); null_best = np.nanmax(NM - mu, axis=1)
    F = pd.DataFrame([dict(mrizka="H1", doteku=len(bar), nejlepsi_excess_R=real_best, null_best_mean=null_best.mean(),
                           null_best_p95=np.quantile(null_best, 0.95), p_family=np.mean(null_best >= real_best),
                           p_lt_005=int((S.p < 0.05).sum()), p_gt_095=int((S.p > 0.95).sum()), konfiguraci=len(S))])
    F.round(4).to_csv(os.path.join(OUT, "bcl_h1_familywise.csv"), index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
    print(F.round(3).to_string())
    print(S.sort_values("excess", ascending=False).head(12).round(3).to_string())
    print(S[(S.smer == "fade") & (S.TP_cyklu == S.SL_cyklu)].round(3).to_string())


if __name__ == "__main__":
    main()
