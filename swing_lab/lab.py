"""
Lab glue: data loading, strategy config -> engine run, statistics, Buy&Hold benchmark.

A strategy config is a plain dict (see systems.py) with:
  side      np.int8 array  +1 long / -1 short / 0 none (signal at close of d)
  emode     0 close / 1 next open / 2 limit / 3 stop
  lim       price array for modes 2/3
  sl, tp, tr  distance arrays in points (np.inf = off)
  tr_act, be_r, max_days, xsig, xmode, cost
"""
from __future__ import annotations

import math
import warnings

import numpy as np
import pandas as pd

from engine import REASONS, run
from features import build_daily

warnings.filterwarnings("ignore")

POINT_USD = 50.0
DEFAULT_COST = 0.5          # points per round trip (commission + slippage), stress-tested at 1.0 / 1.5
# walk-forward selection window: choose systems on 2016-2021 only, then test blind on 2022-2026
WF_END = "2021-12-31"
WF_PERIODS = {
    "disc": ("2016-07-01", "2018-12-31"),
    "val": ("2019-01-01", "2020-06-30"),
    "oos": ("2020-07-01", "2021-12-31"),
}
PERIODS = {                 # Discovery / Validation / true out-of-sample
    "disc": ("2016-07-01", "2021-12-31"),
    "val": ("2022-01-01", "2023-12-31"),
    "oos": ("2024-01-01", "2026-12-31"),
}


class Lab:
    def __init__(self, end: str | None = None, periods: dict | None = None):
        """end: last date used (walk-forward selection); periods: override of PERIODS"""
        self.d, b = build_daily()
        self.d = self.d.copy()
        self.b = b
        self.n = len(self.d)
        self.idx = self.d.index
        d = self.d
        self.px = [np.ascontiguousarray(d[c].values.astype(np.float64)) for c in
                   ("open", "high", "low", "close", "on_open", "on_high", "on_low")]
        self.bars = [np.ascontiguousarray(b[k]) for k in ("o", "h", "l")] + \
                    [np.ascontiguousarray(b["start"].astype(np.int64)), np.ascontiguousarray(b["end"].astype(np.int64))]
        # start after 200-day warm-up so every system sees the same window as the benchmark
        self.start_i = int(np.argmax(d.sma200.notna().values))
        self.end_i = self.n if end is None else int(np.searchsorted(self.idx.values, np.datetime64(end), side="right"))
        self.period_mask = {k: ((self.idx >= a) & (self.idx <= b_)) for k, (a, b_) in (periods or PERIODS).items()}
        self.years = self.idx.year.values
        self.bh = self._buy_hold()
        self.bh[self.end_i:] = 0.0
        self.bh_stats = self.stats(self.bh, np.ones(self.n, dtype=np.int8), None)

    # ------------------------------------------------------------------ benchmark
    def _buy_hold(self):
        c = self.d.close.values
        p = np.zeros(self.n)
        p[self.start_i + 1:] = np.diff(c[self.start_i:])
        # quarterly roll cost ~ 0.5 pt round trip (spread + commissions)
        rolls = pd.read_csv(self._rolls_path(), parse_dates=["roll_time"]).roll_time
        for t in rolls:
            j = np.searchsorted(self.idx.values, np.datetime64(t.normalize()))
            if self.start_i < j < self.n:
                p[j] -= DEFAULT_COST
        return p

    @staticmethod
    def _rolls_path():
        from data_prep import DATA
        return DATA / "rolls.csv"

    # ------------------------------------------------------------------ engine call
    def run(self, cfg: dict, full=False):
        n = self.n
        inf = np.full(n, np.inf)
        side = cfg["side"].astype(np.int8)
        xs = cfg.get("xsig")
        if xs is None:
            xs = np.zeros(n, dtype=np.int8)
        out = run(side, int(cfg.get("emode", 0)), np.asarray(cfg.get("lim", inf), dtype=np.float64),
                  np.asarray(cfg.get("sl", inf), dtype=np.float64),
                  np.asarray(cfg.get("tp", inf), dtype=np.float64),
                  np.asarray(cfg.get("tr", inf), dtype=np.float64),
                  float(cfg.get("tr_act", 0.0)), float(cfg.get("be_r", 0.0)), int(cfg.get("max_days", 0)),
                  xs.astype(np.int8), int(cfg.get("xmode", 0)), float(cfg.get("cost", DEFAULT_COST)),
                  *self.px, *self.bars, self.start_i, self.end_i)
        pnl, pos = out[0], out[1]
        tr = out[2:]
        if full:
            return pnl, pos, self.trades_df(tr)
        return pnl, pos, tr

    def trades_df(self, tr):
        s, e, x, side, ep, xp, p, mae, mfe, rs = tr
        return pd.DataFrame({
            "signal_day": self.idx[s], "entry_day": self.idx[e], "exit_day": self.idx[x],
            "side": side, "entry": ep, "exit": xp, "pnl_pts": p, "pnl_usd": p * POINT_USD,
            "mae": mae, "mfe": mfe, "bars": x - e + 1, "reason": [REASONS.get(int(r), "?") for r in rs]})

    # ------------------------------------------------------------------ statistics
    def stats(self, pnl, pos, tr):
        s0, s1 = self.start_i, self.end_i
        p = pnl[s0:s1]
        eq = np.cumsum(p)
        dd = eq - np.maximum.accumulate(np.maximum(eq, 0))
        mdd = -dd.min() if len(dd) else 0.0
        sd = p.std()
        yrs = len(p) / 252.0
        out = {
            "total": eq[-1] if len(eq) else 0.0,
            "ann": (eq[-1] / yrs) if len(eq) else 0.0,
            "mdd": mdd,
            "sharpe": (p.mean() / sd * math.sqrt(252)) if sd > 0 else 0.0,
            "exposure": float((pos[s0:s1] != 0).mean()),
        }
        dn = p[p < 0]
        dsd = math.sqrt((dn ** 2).sum() / len(p)) if len(p) else 0
        out["sortino"] = p.mean() / dsd * math.sqrt(252) if dsd > 0 else 0.0
        out["mar"] = out["ann"] / mdd if mdd > 0 else 0.0
        # alpha vs buy & hold (OLS of daily pnl on B&H daily pnl)
        if hasattr(self, "bh"):
            x = self.bh[s0:s1]
            xm, ym = x.mean(), p.mean()
            vx = ((x - xm) ** 2).sum()
            beta = ((x - xm) * (p - ym)).sum() / vx if vx > 0 else 0.0
            a = ym - beta * xm
            res = p - a - beta * x
            se = math.sqrt((res ** 2).sum() / max(len(p) - 2, 1) * (1 / len(p) + xm * xm / vx)) if vx > 0 else np.inf
            out["beta"] = beta
            out["alpha_ann"] = a * 252
            out["alpha_t"] = a / se if se > 0 else 0.0
            out["corr_bh"] = np.corrcoef(x, p)[0, 1] if p.std() > 0 else 0.0
        # per-period and per-year
        for k, m in self.period_mask.items():
            ar = np.arange(self.n)
            pm = pnl[m & (ar >= s0) & (ar < s1)]
            out[f"{k}_pnl"] = pm.sum()
            yk = max(len(pm) / 252.0, 1e-9)
            out[f"{k}_ann"] = pm.sum() / yk
        yp = pd.Series(pnl[s0:s1]).groupby(self.years[s0:s1]).sum()
        out["years_pos"] = int((yp > 0).sum())
        out["years"] = int(len(yp))
        out["worst_year"] = float(yp.min())
        if tr is not None:
            tp_ = tr[6] if not isinstance(tr, pd.DataFrame) else tr.pnl_pts.values
            ent = tr[1] if not isinstance(tr, pd.DataFrame) else None
            nt = len(tp_)
            out["trades"] = nt
            out["win"] = float((tp_ > 0).mean()) if nt else 0.0
            out["avg"] = float(tp_.mean()) if nt else 0.0
            gp, gl = tp_[tp_ > 0].sum(), -tp_[tp_ < 0].sum()
            out["pf"] = gp / gl if gl > 0 else (np.inf if gp > 0 else 0.0)
            if not isinstance(tr, pd.DataFrame):
                ex = tr[2]
                out["hold"] = float((ex - ent + 1).mean()) if nt else 0.0
                # trades per period for sample-size checks
                for k, m in self.period_mask.items():
                    sel = m[ex] if nt else np.array([], bool)
                    tk = tp_[sel] if nt else tp_
                    out[f"{k}_n"] = int(len(tk))
                    out[f"{k}_avg"] = float(tk.mean()) if len(tk) else 0.0
                    g1, g2 = tk[tk > 0].sum(), -tk[tk < 0].sum()
                    out[f"{k}_pf"] = g1 / g2 if g2 > 0 else (9.99 if g1 > 0 else 0.0)
        return out

    def evaluate(self, cfg):
        pnl, pos, tr = self.run(cfg)
        return self.stats(pnl, pos, tr), pnl, pos


if __name__ == "__main__":
    import time

    lab = Lab()
    print("B&H:", {k: round(v, 2) for k, v in lab.bh_stats.items()})
    d = lab.d
    # sanity: Connors RSI(2) - long when close > SMA200 and RSI2 < 10, exit close > SMA5
    side = ((d.close > d.sma200) & (d.rsi2 < 10)).values.astype(np.int8)
    xs = (d.close > d.sma5).values.astype(np.int8)
    t = time.time()
    st, pnl, pos = lab.evaluate({"side": side, "xsig": xs})
    print(time.time() - t)
    t = time.time()
    for _ in range(100):
        lab.evaluate({"side": side, "xsig": xs})
    print("per run ms", (time.time() - t) * 10)
    print({k: round(v, 2) for k, v in st.items()})
    _, _, tdf = lab.run({"side": side, "xsig": xs}, full=True)
    print(tdf.tail(10).to_string())
