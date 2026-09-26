"""Build Sessions objects for both data sources and cache them."""
import pickle, time
import pandas as pd
from engine import Sessions, load_bars, daily_adjusted

D = "/tmp/claude-0/data/"

def build():
    va = pd.read_parquet(D + "esvol_daily_raw.parquet")
    ma = pd.read_parquet(D + "es1m_daily_raw.parquet")
    va.index = pd.DatetimeIndex(va.index); ma.index = pd.DatetimeIndex(ma.index)
    adj = daily_adjusted(va, ma)
    for name in ["es1m", "esvol"]:
        t = time.time()
        S = Sessions(load_bars(D + name + ".parquet"), adj)
        pickle.dump(S, open(D + name + "_sess.pkl", "wb"))
        print(name, len(S.dates), S.dates[0].date(), S.dates[-1].date(), "roll days", S.roll.sum(), f"{time.time()-t:.0f}s")

if __name__ == "__main__":
    build()
