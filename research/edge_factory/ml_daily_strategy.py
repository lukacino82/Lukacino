"""Daily walk-forward model turned into an exposure rule, compared with B&H."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data import load
from factory import Factory
from hypotheses import Ctx
from ml import intraday_features, walk_forward

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")

def perf(x):
    eq = (1 + x).cumprod(); yrs = len(x) / 252
    c = eq.iloc[-1] ** (1 / yrs) - 1; dd = (eq / eq.cummax() - 1).min()
    return dict(CAGR=round(c * 100, 2), SR=round(x.mean() / x.std() * np.sqrt(252), 2), DD=round(dd * 100, 1),
                vol=round(x.std() * np.sqrt(252) * 100, 1))

def alpha_t(x, b):
    X = np.c_[np.ones(len(b)), b.values]; be = np.linalg.lstsq(X, x.values, rcond=None)[0]; r = x.values - X @ be
    return round(be[0] / np.sqrt(r.var(ddof=2) / len(x)), 2), round(be[1], 2), round(be[0] * 252 * 100, 2)

def main():
    D = load(); F = Factory(D); C = Ctx(D)
    X = intraday_features(D, F, C)
    T = D.T
    Xd = X.iloc[T.i_close.to_numpy().astype(int)].reset_index(drop=True)
    yrs = T.index.year.to_numpy()
    c5 = F.dfwd["c5"]; n5 = F.dnull["c5"]
    y = c5 - n5
    ok = np.isfinite(y) & (T.index >= "2010-06-01")
    params = dict(objective="regression", learning_rate=0.03, num_leaves=7, min_data_in_leaf=60,
                  feature_fraction=0.7, lambda_l2=10.0, verbose=-1, seed=7)
    pred = np.full(len(T), np.nan); q = {}
    import lightgbm as lgb
    for Y in range(2012, yrs.max() + 1):
        tr = ok & (yrs < Y)
        # embargo: drop the last 5 trading days before the test year (their target overlaps it)
        tri = np.flatnonzero(tr)[:-5]
        te = (yrs == Y) & np.isfinite(Xd.iloc[:, 0].to_numpy() * 0 + 1)
        m = lgb.train(params, lgb.Dataset(Xd.iloc[tri], y[tri]), num_boost_round=250)
        pt = m.predict(Xd.iloc[tri])
        q[Y] = np.quantile(pt, [0.1, 0.3, 0.5, 0.7, 0.9])
        pred[te] = m.predict(Xd.iloc[np.flatnonzero(te)])
    P = pd.Series(pred, index=T.index)
    ret = pd.Series(np.nan_to_num(T.ret.to_numpy()), index=T.index)
    Q = pd.DataFrame({Y: q[Y] for Y in q}).T
    qq = Q.reindex(T.index.year).set_axis(T.index)
    rows = []
    out = {}
    start = "2012-01-01"
    b = ret[start:]
    rows.append(dict(name="B&H", **perf(b), alpha_t=None))
    variants = {
        "Long když predikce > medián (jinak flat)": (P > qq[2]).astype(float),
        "Long když > 30. percentil": (P > qq[1]).astype(float),
        "Long/short decily (+1 nad 90 %, −1 pod 10 %, jinak +1)": np.where(P > qq[4], 1.0, np.where(P < qq[0], -1.0, 1.0)),
        "Páka podle predikce (0 / 1 / 1,5 / 2)": np.select([P < qq[1], P < qq[2], P < qq[3]], [0.0, 1.0, 1.5], 2.0),
    }
    for nm, sig in variants.items():
        s = pd.Series(sig, index=T.index).where(P.notna())
        expo = s.rolling(5, min_periods=1).mean().shift().fillna(1.0)  # 5-day horizon -> average of last 5 signals
        x = (expo * ret)[start:]
        cost = (expo.diff().abs() * 0.5 / T.C).fillna(0)[start:]
        xn = x - cost
        at, beta, aa = alpha_t(xn, b)
        rows.append(dict(name=nm, **perf(xn), alpha_t=at, beta=beta, alpha_ann=aa, avg_expo=round(expo[start:].mean(), 2),
                         **{f"SR_{a[:4]}": round(xn[a:z].mean() / xn[a:z].std() * np.sqrt(252), 2) for a, z in
                            (("2012", "2016"), ("2017", "2021"), ("2022", "2026"))}))
        out[nm] = xn
    lev = pd.DataFrame(out)
    R = pd.DataFrame(rows)
    R.to_csv(os.path.join(OUT, "ml_daily_strategy.csv"), index=False)
    lev.assign(bh=b).to_parquet(os.path.join(OUT, "ml_daily_series.parquet"))
    pd.set_option("display.width", 250)
    print(R.to_string())
    # B&H at the same average exposure for the leverage variant
    for nm in variants:
        ae = R.set_index("name").loc[nm, "avg_expo"]
        print(nm, "B&H stejná expozice", perf(b * ae))

if __name__ == "__main__":
    main()
