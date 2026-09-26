"""
Multi-swing portfolio: plug any number of systems in/out via portfolio_config.json
(enabled yes/no, contracts, direction) and compare the combined equity with Buy & Hold.

Two ways to use alpha:
  STANDALONE   trade only the enabled swing systems (flat most of the time)
  CORE+SAT     hold 1 ES contract permanently (B&H core) + swing systems on top as satellite

Each system runs independently with its own position (a real multi-strategy book: two systems
can be long at the same time -> 2 contracts). max_contracts caps the aggregate exposure by
ranking systems in config order.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import systems as S
from canonical import canonical
from lab import Lab

HERE = Path(__file__).resolve().parent
CONFIG = HERE / "portfolio_config.json"


def load_config(path=CONFIG):
    return json.loads(Path(path).read_text())


def run_portfolio(lab: Lab, conf: dict, cost=None):
    setups = {s[0]: s for s in S.setups(lab.d)}
    exits = {e[0]: e for e in S.exits(lab.d)}
    reg = S.regimes(lab.d)
    canon = canonical(lab.d)
    cost = conf.get("cost_pts", 0.5) if cost is None else cost
    parts, trades = {}, []
    for sysd in conf["systems"]:
        if str(sysd.get("enabled", "yes")).lower() not in ("yes", "true", "1"):
            continue
        if "canonical" in sysd:
            # published rule with fixed parameters (canonical.py)
            cfg = dict(canon[sysd["canonical"]], cost=cost)
        else:
            # any grid system: setup x regime x exit x side from systems.py
            cfg = S.build_cfg(lab.d, setups[sysd["setup"]], exits[sysd["exit"]], int(sysd["side"]),
                              reg[sysd["regime"]], cost)
        pnl, pos, tdf = lab.run(cfg, full=True)
        k = float(sysd.get("contracts", 1))
        parts[sysd["id"]] = (pnl * k, pos * k)
        tdf["system"] = sysd["id"]
        tdf["pnl_pts"] *= k
        trades.append(tdf)
    if not parts:
        raise ValueError("no enabled systems")
    pnl = pd.DataFrame({k: v[0] for k, v in parts.items()}, index=lab.idx)
    pos = pd.DataFrame({k: v[1] for k, v in parts.items()}, index=lab.idx)
    cap = conf.get("max_contracts")
    if cap:
        # scale down days where aggregate exposure exceeds the cap (approximation of skipped signals)
        tot = pos.abs().sum(1)
        f = np.where(tot > cap, cap / tot.replace(0, 1), 1.0)
        pnl = pnl.mul(f, axis=0)
    total = pnl.sum(1).values
    agg_pos = np.sign(pos.sum(1).values).astype(np.int8)
    tr = pd.concat(trades, ignore_index=True) if trades else pd.DataFrame()
    st = lab.stats(total, agg_pos, tr)
    core = total + lab.bh
    st_core = lab.stats(core, np.ones(lab.n, np.int8), None)
    return dict(pnl=pnl, total=total, stats=st, core_sat=core, core_stats=st_core, trades=tr)


if __name__ == "__main__":
    lab = Lab()
    res = run_portfolio(lab, load_config())
    keys = ["total", "ann", "mdd", "sharpe", "mar", "alpha_t", "beta", "exposure", "trades", "win", "pf"]
    print("B&H      ", {k: round(float(lab.bh_stats.get(k, np.nan)), 2) for k in keys if k in lab.bh_stats})
    print("PORTFOLIO", {k: round(float(res["stats"][k]), 2) for k in keys})
    print("CORE+SAT ", {k: round(float(res["core_stats"][k]), 2) for k in keys if k in res["core_stats"]})
    print(res["pnl"].corr().round(2))
