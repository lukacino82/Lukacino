from __future__ import annotations
import os, re, math, warnings
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"
OUT.mkdir(parents=True, exist_ok=True)
DATA = Path(os.environ.get("ES2008_PATH", "out/ES2008.txt"))
COST = 0.50  # ES points round-trip baseline friction
PERIODS = {
    "DISC_2008_2016": ("2008-01-01", "2016-12-31"),
    "VAL_2017_2021": ("2017-01-01", "2021-12-31"),
    "TEST_2022_2026": ("2022-01-01", "2026-12-31"),
    "FULL": ("2008-01-01", "2026-12-31"),
}
ENTRY_TIMES = ["09:30","10:00","10:30","11:00","11:30","12:00","12:30","13:00","13:30","14:00","14:30","15:00"]
HORIZONS = [30, 60, 90, 120, 180, 9999]  # 9999 = EOD
TPS = [5, 8, 10, 12, 15, 20, 25]
SL_MULTS = [1, 1.5, 2, 3, 5, 7.5, 10]
PREV_BINS = [-9999, -20, -10, -5, 0, 5, 10, 20, 9999]

def norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())

def load_raw(path: Path):
    if not path.exists():
        raise FileNotFoundError(path)
    first = path.open("r", errors="ignore").readline()
    sep = "\\t" if "\\t" in first and first.count("\\t") > first.count(",") else ","
    wanted = {"date","time","open","high","low","last","close","volume","vol"}
    pieces=[]
    for ch in pd.read_csv(
        path, sep=sep, chunksize=700_000, low_memory=False, skipinitialspace=True,
        usecols=lambda c: norm(str(c).strip().strip("<>")) in wanted
    ):
        ren={}
        for c in ch.columns:
            n=norm(str(c).strip().strip("<>"))
            if n=="date": ren[c]="date"
            elif n=="time": ren[c]="time"
            elif n=="open": ren[c]="open"
            elif n=="high": ren[c]="high"
            elif n=="low": ren[c]="low"
            elif n in ("last","close"): ren[c]="close"
            elif n in ("volume","vol"): ren[c]="volume"
        ch=ch.rename(columns=ren)
        req={"date","time","open","high","low","close"}
        if not req.issubset(ch.columns):
            raise RuntimeError(f"Missing required columns after normalization: {list(ch.columns)}")
        dt = pd.to_datetime(ch["date"].astype(str).str.strip()+" "+ch["time"].astype(str).str.strip(), errors="coerce")
        z = pd.DataFrame({
            "ts":dt,
            "open":pd.to_numeric(ch["open"],errors="coerce").astype("float32"),
            "high":pd.to_numeric(ch["high"],errors="coerce").astype("float32"),
            "low":pd.to_numeric(ch["low"],errors="coerce").astype("float32"),
            "close":pd.to_numeric(ch["close"],errors="coerce").astype("float32"),
        })
        pieces.append(z.dropna())
    df=pd.concat(pieces,ignore_index=True)
    df=df.drop_duplicates("ts").sort_values("ts").reset_index(drop=True)
    return df

def build_sessions(df):
    # Dataset timestamps are treated as US/Eastern local clock, consistent with prior repository research.
    df["date"]=df.ts.dt.normalize()
    df["hm"]=df.ts.dt.hour*60+df.ts.dt.minute
    # Keep RTH minute bars 09:30-15:59.
    r=df[(df.hm>=570)&(df.hm<960)].copy()
    r["minute"]=r.hm-570
    days=[]
    byday={}
    for d,g in r.groupby("date",sort=True):
        if len(g)<300: continue
        g=g.sort_values("ts").reset_index(drop=True)
        byday[pd.Timestamp(d)]=g
        days.append(pd.Timestamp(d))
    # daily feature table
    rows=[]
    for d in days:
        g=byday[d]
        rows.append((d,float(g.open.iloc[0]),float(g.high.max()),float(g.low.min()),float(g.close.iloc[-1])))
    T=pd.DataFrame(rows,columns=["date","O","H","L","C"]).set_index("date")
    T["pC"]=T.C.shift(1)
    T["ret"]=T.C/T.pC-1
    tr=np.maximum(T.H-T.L,np.maximum((T.H-T.pC).abs(),(T.L-T.pC).abs()))
    T["atr20"]=tr.rolling(20).mean().shift(1)
    T["ma200"]=T.C.rolling(200).mean().shift(1)
    T["bull"]=(T.pC>T.ma200)
    T["rv20"]=T.ret.rolling(20).std().shift(1)*np.sqrt(252)
    T["ath_prev"]=T.C.cummax().shift(1)
    T["dd_ath"]=T.pC/T.ath_prev-1
    move=T.C.diff().abs()
    T["eff20"]=(T.pC-T.C.shift(21)).abs()/move.shift(1).rolling(20).sum()
    T["r20"]=T.pC/T.C.shift(21)-1
    T["trend_state"]=np.select(
        [T.r20>0.04, T.r20<-0.04, T.eff20<0.18],
        ["UP","DOWN","BALANCE"], default="MIXED")
    q=T.rv20.expanding(min_periods=100).quantile(.75)
    T["vol_state"]=np.where(T.rv20>q,"HIGH_VOL","NORMAL_VOL")
    return byday,T

def get_entry(g, hm):
    h,m=map(int,hm.split(":")); target=h*60+m
    x=g[g.hm>=target]
    if x.empty: return None
    i=int(x.index[0])
    return i,float(g.open.iloc[i])

def horizon_end(g,i,h):
    return min(len(g)-1, i+h-1) if h<9999 else len(g)-1

def trade_path(g,i,entry,tp,sl,h):
    e=horizon_end(g,i,h)
    hh=g.high.to_numpy()[i:e+1].astype(float)
    ll=g.low.to_numpy()[i:e+1].astype(float)
    cc=g.close.to_numpy()[i:e+1].astype(float)
    up=np.flatnonzero(hh>=entry+tp)
    dn=np.flatnonzero(ll<=entry-sl)
    iu=int(up[0]) if len(up) else 10**9
    idn=int(dn[0]) if len(dn) else 10**9
    # conservative if same minute: stop first
    if idn<=iu and idn<10**9:
        gross=-sl; outcome="SL"; bars=idn+1
    elif iu<idn and iu<10**9:
        gross=tp; outcome="TP"; bars=iu+1
    else:
        gross=float(cc[-1]-entry); outcome="TIME"; bars=len(cc)
    return gross-COST,outcome,bars,float(hh.max()-entry),float(entry-ll.min())

def maxdd(x):
    c=np.cumsum(np.asarray(x,float))
    peak=np.maximum.accumulate(np.r_[0,c])
    dd=np.r_[0,c]-peak
    return float(dd.min())

def perf(vals):
    a=np.asarray(vals,float)
    if len(a)==0: return {}
    pos=a[a>0].sum(); neg=-a[a<0].sum()
    return {
        "n":len(a),"net_pts":a.sum(),"avg_pts":a.mean(),
        "win_rate":(a>0).mean(),"profit_factor":pos/neg if neg>0 else np.nan,
        "maxdd_pts":maxdd(a)
    }

def in_period(d, p):
    a,b=PERIODS[p]; return pd.Timestamp(a)<=d<=pd.Timestamp(b)

def main():
    print("loading",DATA)
    df=load_raw(DATA)
    print("rows",len(df),"from",df.ts.min(),"to",df.ts.max())
    byday,T=build_sessions(df)
    print("sessions",len(T),T.index.min(),T.index.max())
    T.to_csv(OUT/"daily_features.csv")

    # Precompute entry objects to avoid repeated slicing.
    entries=[]
    for d,g in byday.items():
        if d not in T.index: continue
        feat=T.loc[d]
        for et in ENTRY_TIMES:
            z=get_entry(g,et)
            if not z: continue
            i,ep=z
            prev=None
            if i>=60:
                prev=float(g.close.iloc[i-1]-g.open.iloc[i-60])
            entries.append({
                "date":d,"time":et,"i":i,"entry":ep,"g":g,
                "prev60":prev,"bull":bool(feat.bull) if pd.notna(feat.bull) else False,
                "trend_state":feat.trend_state,"vol_state":feat.vol_state,
                "dd_ath":feat.dd_ath,"atr20":feat.atr20,
            })
    # 1) raw hourly hit-rate atlas
    hitrows=[]
    for et in ENTRY_TIMES:
        E=[e for e in entries if e["time"]==et]
        for h in HORIZONS:
            for tp in [5,8,10,12,15,20,25]:
                for p in PERIODS:
                    sub=[e for e in E if in_period(e["date"],p)]
                    if not sub: continue
                    hits=0; reached=[]
                    for e in sub:
                        end=horizon_end(e["g"],e["i"],h)
                        hh=e["g"].high.to_numpy()[e["i"]:end+1].astype(float)
                        ok=bool(np.any(hh>=e["entry"]+tp))
                        hits+=ok
                        if ok: reached.append(int(np.flatnonzero(hh>=e["entry"]+tp)[0])+1)
                    hitrows.append([p,et,h,tp,len(sub),hits/len(sub),np.median(reached) if reached else np.nan])
    HIT=pd.DataFrame(hitrows,columns=["period","entry_time","horizon_min","target_pts","n","hit_rate","median_minutes_to_target"])
    HIT.to_csv(OUT/"hourly_long_hit_rate.csv",index=False)

    # 2) inverse RRR grid, full path
    rows=[]; trade_cache={}
    for et in ENTRY_TIMES:
        E=[e for e in entries if e["time"]==et]
        for h in [60,120,180,9999]:
            for tp in TPS:
                for mult in SL_MULTS:
                    sl=tp*mult
                    key=(et,h,tp,sl)
                    trades=[]
                    for e in E:
                        net,outcome,bars,mfe,mae=trade_path(e["g"],e["i"],e["entry"],tp,sl,h)
                        trades.append((e["date"],net,outcome,bars,mfe,mae,e))
                    trade_cache[key]=trades
                    for p in PERIODS:
                        a=[x for x in trades if in_period(x[0],p)]
                        vals=[x[1] for x in a]
                        m=perf(vals)
                        if not m: continue
                        rows.append([p,et,h,tp,sl,mult,m["n"],m["win_rate"],m["avg_pts"],m["net_pts"],m["profit_factor"],m["maxdd_pts"],
                                     np.mean([x[2]=="TP" for x in a]),np.mean([x[2]=="SL" for x in a]),np.mean([x[4] for x in a]),np.mean([x[5] for x in a])])
    G=pd.DataFrame(rows,columns=["period","entry_time","horizon_min","tp_pts","sl_pts","sl_over_tp","n","win_rate","avg_net_pts","net_pts","profit_factor","maxdd_pts","tp_rate","sl_rate","avg_mfe","avg_mae"])
    G.to_csv(OUT/"inverse_rrr_grid.csv",index=False)

    # Discovery ranking only; then evaluate fixed configs on VAL/TEST.
    D=G[G.period=="DISC_2008_2016"].copy()
    D=D[(D.n>=1200)&(D.avg_net_pts>0)&(D.profit_factor>1)]
    D["score"]=D.avg_net_pts*np.minimum(D.profit_factor,2.0)*np.sqrt(D.n)
    top=D.sort_values("score",ascending=False).head(20)[["entry_time","horizon_min","tp_pts","sl_pts","sl_over_tp"]]
    fixed=[]
    for _,cfg in top.iterrows():
        mask=(G.entry_time==cfg.entry_time)&(G.horizon_min==cfg.horizon_min)&(G.tp_pts==cfg.tp_pts)&(G.sl_pts==cfg.sl_pts)
        z=G[mask].copy()
        for _,r in z.iterrows():
            fixed.append(r.to_dict())
    FIX=pd.DataFrame(fixed)
    FIX.to_csv(OUT/"discovery_fixed_top20_evaluation.csv",index=False)

    # 3) previous-hour condition for fixed top configs
    prows=[]
    for ci,cfg in top.reset_index(drop=True).iterrows():
        key=(cfg.entry_time,int(cfg.horizon_min),float(cfg.tp_pts),float(cfg.sl_pts))
        trades=trade_cache[key]
        for lo,hi in zip(PREV_BINS[:-1],PREV_BINS[1:]):
            for p in PERIODS:
                a=[x for x in trades if in_period(x[0],p) and x[6]["prev60"] is not None and lo < x[6]["prev60"] <= hi]
                vals=[x[1] for x in a]
                if len(vals)<30: continue
                m=perf(vals)
                prows.append([ci+1,p,cfg.entry_time,int(cfg.horizon_min),cfg.tp_pts,cfg.sl_pts,lo,hi,len(vals),m["win_rate"],m["avg_pts"],m["net_pts"],m["profit_factor"],m["maxdd_pts"]])
    PREV=pd.DataFrame(prows,columns=["rank_disc","period","entry_time","horizon_min","tp_pts","sl_pts","prev60_lo","prev60_hi","n","win_rate","avg_net_pts","net_pts","profit_factor","maxdd_pts"])
    PREV.to_csv(OUT/"previous_hour_condition.csv",index=False)

    # 4) regime breakdown for discovery-fixed configs
    rrows=[]
    for ci,cfg in top.reset_index(drop=True).iterrows():
        key=(cfg.entry_time,int(cfg.horizon_min),float(cfg.tp_pts),float(cfg.sl_pts))
        trades=trade_cache[key]
        for dim in ["bull","trend_state","vol_state"]:
            groups=sorted(set(str(x[6][dim]) for x in trades))
            for grp in groups:
                for p in PERIODS:
                    a=[x for x in trades if in_period(x[0],p) and str(x[6][dim])==grp]
                    if len(a)<40: continue
                    m=perf([x[1] for x in a])
                    rrows.append([ci+1,p,cfg.entry_time,int(cfg.horizon_min),cfg.tp_pts,cfg.sl_pts,dim,grp,m["n"],m["win_rate"],m["avg_pts"],m["profit_factor"],m["maxdd_pts"]])
    REG=pd.DataFrame(rrows,columns=["rank_disc","period","entry_time","horizon_min","tp_pts","sl_pts","dimension","regime","n","win_rate","avg_net_pts","profit_factor","maxdd_pts"])
    REG.to_csv(OUT/"fixed_top20_regime_breakdown.csv",index=False)

    # 5) yearly evaluation + equity for top 5 fixed discovery configs.
    yrs=sorted(set(T.index.year))
    yrows=[]; eqrows=[]
    top5=top.head(5).reset_index(drop=True)
    # ES B&H proxy: RTH close-to-close points, not S&P total return.
    bh_daily=T.C.diff().fillna(0)
    for year in yrs:
        yb=bh_daily[T.index.year==year].sum()
        yrows.append({"strategy":"ES_B&H_1contract","year":year,"net_pts":yb})
    for ci,cfg in top5.iterrows():
        key=(cfg.entry_time,int(cfg.horizon_min),float(cfg.tp_pts),float(cfg.sl_pts))
        trades=trade_cache[key]
        name=f"R{ci+1}_{cfg.entry_time}_H{int(cfg.horizon_min)}_TP{cfg.tp_pts:g}_SL{cfg.sl_pts:g}"
        for year in yrs:
            vals=[x[1] for x in trades if x[0].year==year]
            yrows.append({"strategy":name,"year":year,"net_pts":sum(vals)})
        cum=0.0
        for x in trades:
            cum+=x[1]
            eqrows.append({"date":x[0],"strategy":name,"equity_pts":cum})
    # B&H daily cumulative
    cum=0.0
    for d,v in bh_daily.items():
        cum+=float(v)
        eqrows.append({"date":d,"strategy":"ES_B&H_1contract","equity_pts":cum})
    Y=pd.DataFrame(yrows); E=pd.DataFrame(eqrows)
    Y.to_csv(OUT/"top5_yearly_points.csv",index=False)
    E.to_csv(OUT/"top5_equity_points.csv",index=False)

    # Charts
    def savefig(name):
        plt.tight_layout(); plt.savefig(OUT/name,dpi=150,bbox_inches="tight"); plt.close()
    # hit-rate heatmap, EOD targets
    h0=HIT[(HIT.period=="FULL")&(HIT.horizon_min==9999)].pivot(index="entry_time",columns="target_pts",values="hit_rate")
    plt.figure(figsize=(9,5)); plt.imshow(h0.values,aspect="auto",vmin=0,vmax=1)
    plt.xticks(range(len(h0.columns)),h0.columns); plt.yticks(range(len(h0.index)),h0.index)
    plt.colorbar(label="P(target reached by EOD)"); plt.xlabel("Target points"); plt.ylabel("Entry time")
    plt.title("ES2008 Long target hit-rate by RTH entry time")
    savefig("hourly_hit_rate_heatmap.png")
    # discovery inverse RRR avg expectancy for TP15, H180
    g0=G[(G.period=="DISC_2008_2016")&(G.tp_pts==15)&(G.horizon_min==180)].pivot(index="entry_time",columns="sl_over_tp",values="avg_net_pts")
    plt.figure(figsize=(9,5)); plt.imshow(g0.values,aspect="auto")
    plt.xticks(range(len(g0.columns)),g0.columns); plt.yticks(range(len(g0.index)),g0.index)
    plt.colorbar(label="Avg net points/trade"); plt.xlabel("SL / TP"); plt.ylabel("Entry time")
    plt.title("Discovery: TP 15 points, inverse-RRR expectancy surface")
    savefig("inverse_rrr_tp15_h180_heatmap.png")
    # top5 + B&H equity
    p=E.pivot(index="date",columns="strategy",values="equity_pts").sort_index().ffill().fillna(0)
    plt.figure(figsize=(11,6))
    for c in p.columns: plt.plot(p.index,p[c],label=c,linewidth=1.2)
    plt.legend(fontsize=7,ncol=2); plt.ylabel("Cumulative ES points"); plt.title("Discovery-fixed strategies vs ES Buy & Hold (1 contract)")
    savefig("top5_equity_vs_buyhold.png")
    # yearly excess heatmap
    yp=Y.pivot(index="strategy",columns="year",values="net_pts")
    if "ES_B&H_1contract" in yp.index:
        bh=yp.loc["ES_B&H_1contract"]
        ex=yp.drop(index="ES_B&H_1contract").subtract(bh,axis=1)
        plt.figure(figsize=(12,4)); plt.imshow(ex.values,aspect="auto")
        plt.xticks(range(len(ex.columns)),ex.columns,rotation=45); plt.yticks(range(len(ex.index)),ex.index,fontsize=7)
        plt.colorbar(label="Excess ES points vs B&H"); plt.title("Year-by-year excess vs ES Buy & Hold")
        savefig("top5_yearly_excess_heatmap.png")

    meta = pd.DataFrame([{
        "source":str(DATA),"rows_1m":len(df),"sessions":len(T),"first":df.ts.min(),"last":df.ts.max(),
        "rth":"09:30-16:00 ET","cost_points_roundtrip":COST,
        "intrabar_rule":"if TP and SL touched in same 1m bar -> SL first (conservative)",
        "selection":"top configs selected ONLY on DISC 2008-2016, then fixed for VAL 2017-2021 and TEST 2022-2026",
        "benchmark":"continuous ES close-to-close points; proxy for S&P exposure, NOT S&P 500 total return/dividends"
    }])
    meta.to_csv(OUT/"methodology.csv",index=False)
    print("DONE", sorted(p.name for p in OUT.iterdir()))

if __name__=="__main__":
    main()
