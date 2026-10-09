"""Family-level information diagnostics on the factory table."""
import os
import numpy as np, pandas as pd
from scipy.stats import spearmanr

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")

def run():
    R = pd.read_csv(os.path.join(OUT, "factory_results.csv"))
    nl = (R.n_VAL + R.n_TEST).clip(1)
    R["t_LATER"] = (R.t_VAL.fillna(0) * np.sqrt(R.n_VAL.clip(0)) + R.t_TEST.fillna(0) * np.sqrt(R.n_TEST.clip(0))) / np.sqrt(nl)
    g = R.groupby("family")
    d = pd.DataFrame({"tests": g.size(),
                      "share_t2": g.t_DISC.apply(lambda x: (x.abs() > 2).mean() * 100),
                      "sign_holds": g.ex_LATER.apply(lambda x: (x > 0).mean() * 100),
                      "sign_holds_t2": g.apply(lambda x: (x[x.t_DISC.abs() > 2].ex_LATER > 0).mean() * 100),
                      "corr": g.apply(lambda x: spearmanr(x.t_DISC.abs(), x.t_LATER).correlation),
                      "net_all": g.apply(lambda x: ((x.net_DISC > 0) & (x.net_VAL > 0) & (x.net_TEST > 0)).mean() * 100)}).round(2)
    tot = dict(tests=len(R), share_t2=(R.t_DISC.abs() > 2).mean() * 100, sign_holds=(R.ex_LATER > 0).mean() * 100,
               sign_holds_t2=(R[R.t_DISC.abs() > 2].ex_LATER > 0).mean() * 100,
               corr=spearmanr(R.t_DISC.abs(), R.t_LATER).correlation,
               net_all=((R.net_DISC > 0) & (R.net_VAL > 0) & (R.net_TEST > 0)).mean() * 100)
    d.loc["CELKEM"] = pd.Series(tot).round(2)
    d.to_csv(os.path.join(OUT, "family_diag.csv"))
    R.to_csv(os.path.join(OUT, "factory_results.csv"), index=False)
    return R, d

if __name__ == "__main__":
    R, d = run()
    pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 80)
    print(d.to_string())
    c = ["name", "horizon", "dir", "n_DISC", "t_DISC", "t_VAL", "t_TEST", "ex_DISC", "ex_VAL", "ex_TEST", "net_DISC", "net_VAL", "net_TEST"]
    cons = R[(R.t_DISC.abs() > 2) & (R.t_VAL > 1) & (R.t_TEST > 1)]
    print(len(cons)); print(cons[c].round(2).to_string())
