from __future__ import annotations
import os, re, warnings
from pathlib import Path
import numpy as np
import pandas as pd
warnings.filterwarnings("ignore")

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"out"; OUT.mkdir(parents=True,exist_ok=True)
DATA=Path(os.environ.get("ES2008_PATH","extracted/ES2008.txt"))
COST=0.50
ENTRY_TIMES=["09:30","10:00","10:30","11:00","11:30","12:00","12:30","13:00","13:30","14:00","14:30","15:00"]
TPS=np.array([5.,8.,10.,12.,15.,20.,25.])
MULTS=np.array([1.,1.5,2.,3.,5.,7.5,10.])
HORIZONS=[60,120,180,9999]
PERIODS={"DISC":("2008-01-01","2016-12-31"),"VAL":("2017-01-01","2021-12-31"),"TEST":("2022-01-01","2026-12-31"),"FULL":("2008-01-01","2026-12-31")}
POINT_BINS=[-1e9,-20,-10,-5,0,5,10,20,1e9]
ATR_BINS=[-1e9,-1.5,-1,-.5,0,.5,1,1.5,1e9]
GAP_ATR_BINS=[-1e9,-1,-.5,-.25,0,.25,.5,1,1e9]
DD_BINS=[-1,-.20,-.10,-.05,0.001]
RV_BINS=[0,.12,.20,.30,9]
STREAK_BINS=[0,1,2,3,4,99]

def norm(s): return re.sub(r"[^a-z0-9]","",str(s).lower())
def period_mask(dates,p):
    a,b=PERIODS[p]; return (dates>=np.datetime64(a))&(dates<=np.datetime64(b))

def load_raw(path):
    first=path.open("r",errors="ignore").readline()
    sep="\t" if "\t" in first and first.count("\t")>first.count(",") else ","
    wanted={"date","time","open","high","low","last","close","volume","vol"}
    chunks=[]
    for ch in pd.read_csv(path,sep=sep,chunksize=750_000,low_memory=False,skipinitialspace=True,
                          usecols=lambda c:norm(str(c).strip().strip("<>")) in wanted):
        ren={}
        for c in ch.columns:
            n=norm(str(c).strip().strip("<>"))
            if n in ("date","time","open","high","low"): ren[c]=n
            elif n in ("last","close"): ren[c]="close"
            elif n in ("volume","vol"): ren[c]="volume"
        ch=ch.rename(columns=ren)
        dt=pd.to_datetime(ch["date"].astype(str).str.strip()+" "+ch["time"].astype(str).str.strip(),errors="coerce")
        z=pd.DataFrame({"ts":dt,"open":pd.to_numeric(ch.open,errors="coerce").astype("float32"),
                        "high":pd.to_numeric(ch.high,errors="coerce").astype("float32"),
                        "low":pd.to_numeric(ch.low,errors="coerce").astype("float32"),
                        "close":pd.to_numeric(ch.close,errors="coerce").astype("float32"),
                        "volume":pd.to_numeric(ch.volume,errors="coerce").fillna(0).astype("float32") if "volume" in ch else 0})
        chunks.append(z.dropna(subset=["ts","open","high","low","close"]))
    return pd.concat(chunks,ignore_index=True).drop_duplicates("ts").sort_values("ts").reset_index(drop=True)

def anchored_vwap(g):
    tp=(g.high.astype(float)+g.low.astype(float)+g.close.astype(float))/3
    v=g.volume.astype(float)
    den=v.cumsum().replace(0,np.nan)
    return (tp*v).cumsum()/den

def build(df):
    df["date"]=df.ts.dt.normalize(); df["hm"]=df.ts.dt.hour*60+df.ts.dt.minute
    by={}
    daily=[]
    for d,g0 in df.groupby("date",sort=True):
        r=g0[(g0.hm>=570)&(g0.hm<960)].copy()
        if len(r)<300: continue
        r=r.sort_values("ts").reset_index(drop=True)
        r["vwapD"]=anchored_vwap(r)
        d=pd.Timestamp(d); by[d]=r
        # overnight bars from prior 18:00 through 09:29 if present in local date grouping is imperfect;
        # use current day's pre-09:30 rows as conservative overnight proxy.
        pre=g0[g0.hm<570]
        on_open=float(pre.open.iloc[0]) if len(pre) else np.nan
        on_close=float(pre.close.iloc[-1]) if len(pre) else np.nan
        on_hi=float(pre.high.max()) if len(pre) else np.nan
        on_lo=float(pre.low.min()) if len(pre) else np.nan
        daily.append([d,float(r.open.iloc[0]),float(r.high.max()),float(r.low.min()),float(r.close.iloc[-1]),
                      float(r.volume.sum()),on_open,on_close,on_hi,on_lo])
    T=pd.DataFrame(daily,columns=["date","O","H","L","C","Vol","onO","onC","onH","onL"]).set_index("date")
    T["pC"]=T.C.shift(); T["ret"]=T.C/T.pC-1
    tr=np.maximum(T.H-T.L,np.maximum((T.H-T.pC).abs(),(T.L-T.pC).abs()))
    T["atr20"]=tr.rolling(20).mean().shift()
    T["rv20"]=T.ret.rolling(20).std().shift()*np.sqrt(252)
    T["ma200"]=T.C.rolling(200).mean().shift()
    T["bull"]=T.pC>T.ma200
    T["gap_pts"]=T.O-T.pC; T["gap_atr"]=T.gap_pts/T.atr20
    T["on_ret_pts"]=T.onC-T.onO
    T["ath_prev"]=T.C.cummax().shift(); T["dd_ath"]=T.pC/T.ath_prev-1
    T["r20"]=T.pC/T.C.shift(21)-1
    move=T.C.diff().abs(); T["eff20"]=(T.pC-T.C.shift(21)).abs()/move.shift().rolling(20).sum()
    T["trend_state"]=np.select([T.r20>0.04,T.r20<-0.04,T.eff20<0.18],["UP","DOWN","BALANCE"],default="MIXED")
    # prior daily streaks, known before today's entry
    down=(T.ret.shift()<0).astype(int); up=(T.ret.shift()>0).astype(int)
    T["down_streak"]=down.groupby((down==0).cumsum()).cumsum()
    T["up_streak"]=up.groupby((up==0).cumsum()).cumsum()
    T["ret3_prev"]=T.C.shift(1)/T.C.shift(4)-1
    T["ret5_prev"]=T.C.shift(1)/T.C.shift(6)-1
    return by,T

def first_touch(ph,pl,tp,sl):
    u=np.flatnonzero(ph>=tp); d=np.flatnonzero(pl>=sl)
    iu=int(u[0]) if len(u) else 10**6; idn=int(d[0]) if len(d) else 10**6
    return iu,idn

def metrics(a):
    a=np.asarray(a,float)
    if len(a)==0:return None
    pos=a[a>0].sum(); neg=-a[a<0].sum(); c=np.cumsum(a); peak=np.maximum.accumulate(np.r_[0,c])
    return dict(n=len(a),win_rate=(a>0).mean(),avg=a.mean(),net=a.sum(),
                pf=pos/neg if neg>0 else np.nan,mdd=(np.r_[0,c]-peak).min())

def label_bin(x,bins,prefix):
    if not np.isfinite(x): return None
    for a,b in zip(bins[:-1],bins[1:]):
        if a < x <= b:
            return f"{prefix}({a:g},{b:g}]"
    return None

def main():
    df=load_raw(DATA); by,T=build(df)
    print("DATA",len(df),df.ts.min(),df.ts.max(),"sessions",len(T),flush=True)
    states=[]; paths={}
    for d,g in by.items():
        if d not in T.index: continue
        f=T.loc[d]
        for et in ENTRY_TIMES:
            h,m=map(int,et.split(":")); target=h*60+m
            ix=np.flatnonzero(g.hm.to_numpy()>=target)
            if len(ix)==0: continue
            i=int(ix[0]); entry=float(g.open.iloc[i])
            prev30=float(g.close.iloc[i-1]-g.open.iloc[max(0,i-30)]) if i>=1 else np.nan
            prev60=float(g.close.iloc[i-1]-g.open.iloc[max(0,i-60)]) if i>=1 else np.nan
            prev90=float(g.close.iloc[i-1]-g.open.iloc[max(0,i-90)]) if i>=1 else np.nan
            atr=float(f.atr20) if pd.notna(f.atr20) else np.nan
            vwap=float(g.vwapD.iloc[i-1]) if i>0 and pd.notna(g.vwapD.iloc[i-1]) else np.nan
            dist_vwap=(entry-vwap)/atr if np.isfinite(atr) and atr>0 and np.isfinite(vwap) else np.nan
            state=dict(date=d,time=et,entry=entry,i=i,prev30=prev30,prev60=prev60,prev90=prev90,
                       prev60_atr=prev60/atr if np.isfinite(atr) and atr>0 else np.nan,
                       bull=str(bool(f.bull)) if pd.notna(f.bull) else None,trend=str(f.trend_state),
                       rv20=float(f.rv20) if pd.notna(f.rv20) else np.nan,dd_ath=float(f.dd_ath) if pd.notna(f.dd_ath) else np.nan,
                       gap_atr=float(f.gap_atr) if pd.notna(f.gap_atr) else np.nan,
                       dist_vwap_atr=dist_vwap,down_streak=int(f.down_streak) if pd.notna(f.down_streak) else 0,
                       up_streak=int(f.up_streak) if pd.notna(f.up_streak) else 0,
                       ret3=float(f.ret3_prev) if pd.notna(f.ret3_prev) else np.nan,
                       ret5=float(f.ret5_prev) if pd.notna(f.ret5_prev) else np.nan)
            idx=len(states); states.append(state)
            for hor in HORIZONS:
                e=len(g)-1 if hor==9999 else min(len(g)-1,i+hor-1)
                ph=g.high.to_numpy(dtype=float)[i:e+1]-entry
                pl=entry-g.low.to_numpy(dtype=float)[i:e+1]
                close_ret=float(g.close.iloc[e]-entry)
                paths[(idx,hor)]=(ph,pl,close_ret)
    S=pd.DataFrame(states)
    # predeclared state labels
    labels={}
    labels["bull"]=[str(x) for x in S.bull]
    labels["trend"]=[str(x) for x in S.trend]
    labels["prev60_pts"]=[label_bin(x,POINT_BINS,"p60") for x in S.prev60]
    labels["prev60_atr"]=[label_bin(x,ATR_BINS,"p60a") for x in S.prev60_atr]
    labels["gap_atr"]=[label_bin(x,GAP_ATR_BINS,"gap") for x in S.gap_atr]
    labels["dd_ath"]=[label_bin(x,DD_BINS,"dd") for x in S.dd_ath]
    labels["rv20"]=[label_bin(x,RV_BINS,"rv") for x in S.rv20]
    labels["dist_vwap"]=[label_bin(x,ATR_BINS,"dvwap") for x in S.dist_vwap_atr]
    labels["down_streak"]=[label_bin(float(x),STREAK_BINS,"dn") for x in S.down_streak]
    labels["up_streak"]=[label_bin(float(x),STREAK_BINS,"up") for x in S.up_streak]
    for k,v in labels.items(): S[k+"_state"]=v
    S.to_csv(OUT/"entry_state_table.csv",index=False)

    # Conditional distribution (MFE/MAE) by one-dimensional state, before RRR selection.
    distrows=[]
    dims=[c for c in S.columns if c.endswith("_state")]+["time"]
    for dim in dims:
        for val,idxs in S.groupby(dim,dropna=True).groups.items():
            ids=np.array(list(idxs),dtype=int)
            for hor in HORIZONS:
                mfe=[]; mae=[]; close=[]
                for q in ids:
                    ph,pl,cr=paths[(q,hor)]; mfe.append(np.max(ph)); mae.append(np.max(pl)); close.append(cr)
                for p in PERIODS:
                    pm=period_mask(S.loc[ids,"date"].values.astype("datetime64[ns]"),p)
                    if pm.sum()<80: continue
                    mf=np.asarray(mfe)[pm]; ma=np.asarray(mae)[pm]; cr=np.asarray(close)[pm]
                    distrows.append([dim,str(val),p,hor,int(pm.sum()),np.mean(mf),np.median(mf),np.mean(ma),np.median(ma),np.mean(cr),
                                     *[(mf>=t).mean() for t in TPS]])
    cols=["dimension","state","period","horizon_min","n","mean_mfe","median_mfe","mean_mae","median_mae","mean_close_ret"]+[f"p_mfe_ge_{int(t)}" for t in TPS]
    DIST=pd.DataFrame(distrows,columns=cols); DIST.to_csv(OUT/"conditional_excursion_distribution.csv",index=False)

    # RRR within one-dimensional states. Choose only DISC states with sample >=250 and positive plateau candidates.
    rrows=[]
    for dim in dims:
        groups=S.groupby(dim,dropna=True).groups
        for val,idxs0 in groups.items():
            ids=np.array(list(idxs0),dtype=int)
            for hor in HORIZONS:
                # precompute path for this subset
                for tp in TPS:
                    for mult in MULTS:
                        sl=float(tp*mult); nets=[]
                        for q in ids:
                            ph,pl,cr=paths[(q,hor)]
                            iu,idn=first_touch(ph,pl,float(tp),sl)
                            gross=-sl if idn<=iu and idn<10**6 else (float(tp) if iu<idn and iu<10**6 else cr)
                            nets.append(gross-COST)
                        nets=np.asarray(nets)
                        dates=S.loc[ids,"date"].values.astype("datetime64[ns]")
                        for p in PERIODS:
                            pm=period_mask(dates,p)
                            if pm.sum()<80: continue
                            z=metrics(nets[pm])
                            rrows.append([dim,str(val),p,hor,tp,sl,mult,z["n"],z["win_rate"],z["avg"],z["net"],z["pf"],z["mdd"]])
    R=pd.DataFrame(rrows,columns=["dimension","state","period","horizon_min","tp_pts","sl_pts","sl_over_tp","n","win_rate","avg_net_pts","net_pts","profit_factor","maxdd_pts"])
    R.to_csv(OUT/"conditional_rrr_grid.csv",index=False)

    # Discovery selection with plateau requirement: same state/time/horizon/tp must have >=2 adjacent SL multipliers positive PF>1.
    D=R[(R.period=="DISC")&(R.n>=250)&(R.avg_net_pts>0)&(R.profit_factor>1)].copy()
    D["plateau"]=False
    grpcols=["dimension","state","horizon_min","tp_pts"]
    for _,g in D.groupby(grpcols):
        ms=sorted(g.sl_over_tp.unique())
        keep=set()
        for a,b in zip(ms[:-1],ms[1:]):
            ia=np.where(MULTS==a)[0]; ib=np.where(MULTS==b)[0]
            if len(ia) and len(ib) and abs(int(ia[0])-int(ib[0]))==1: keep.update([a,b])
        if keep:
            D.loc[g[g.sl_over_tp.isin(keep)].index,"plateau"]=True
    DP=D[D.plateau].copy()
    DP["score"]=DP.avg_net_pts*np.sqrt(DP.n)*np.minimum(DP.profit_factor,2)
    top=DP.sort_values("score",ascending=False).head(30)
    top.to_csv(OUT/"discovery_candidates_plateau.csv",index=False)

    # Freeze exact selected definitions and read matching VAL/TEST/FULL rows; no retuning.
    fixed=[]
    keycols=["dimension","state","horizon_min","tp_pts","sl_pts","sl_over_tp"]
    for rank,(_,c) in enumerate(top.iterrows(),1):
        mask=np.ones(len(R),dtype=bool)
        for k in keycols: mask &= (R[k].astype(str)==str(c[k]))
        z=R[mask].copy(); z.insert(0,"rank_disc",rank); fixed.append(z)
    F=pd.concat(fixed,ignore_index=True) if fixed else pd.DataFrame()
    F.to_csv(OUT/"fixed_candidate_evaluation.csv",index=False)

    # Stability summary: require positive in DISC and VAL; TEST reported only.
    stable=[]
    if len(F):
        for rank,g in F.groupby("rank_disc"):
            x={r.period:r for _,r in g.iterrows()}
            if "DISC" not in x: continue
            stable.append([rank,x["DISC"].dimension,x["DISC"].state,x["DISC"].horizon_min,x["DISC"].tp_pts,x["DISC"].sl_pts,
                           x.get("DISC",{}).get("avg_net_pts",np.nan),x.get("VAL",{}).get("avg_net_pts",np.nan),
                           x.get("TEST",{}).get("avg_net_pts",np.nan),x.get("FULL",{}).get("avg_net_pts",np.nan),
                           x.get("DISC",{}).get("n",np.nan),x.get("VAL",{}).get("n",np.nan),x.get("TEST",{}).get("n",np.nan)])
    ST=pd.DataFrame(stable,columns=["rank_disc","dimension","state","horizon_min","tp_pts","sl_pts","disc_avg","val_avg","test_avg","full_avg","disc_n","val_n","test_n"])
    if len(ST):
        ST["disc_val_survive"]=(ST.disc_avg>0)&(ST.val_avg>0)
        ST["all3_positive"]=ST.disc_val_survive&(ST.test_avg>0)
    ST.to_csv(OUT/"stability_summary.csv",index=False)

    pd.DataFrame([{"rows_1m":len(df),"sessions":len(T),"first":df.ts.min(),"last":df.ts.max(),"cost_rt_pts":COST,
        "same_bar_rule":"SL first","selection":"predeclared 1D states; discovery 2008-2016; plateau across adjacent SL multipliers; fixed VAL/TEST",
        "warning":"2022-2026 is pseudo-OOS only due prior inspection"}]).to_csv(OUT/"methodology.csv",index=False)
    print("CANDIDATES",len(DP),"TOP",len(top),"SURVIVE_DISC_VAL",int(ST.disc_val_survive.sum()) if len(ST) else 0,
          "ALL3",int(ST.all3_positive.sum()) if len(ST) else 0,flush=True)

if __name__=="__main__": main()
