from __future__ import annotations
import os, re, warnings
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
warnings.filterwarnings("ignore")

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"out"; OUT.mkdir(parents=True,exist_ok=True)
DATA=Path(os.environ.get("ES2008_PATH","extracted/ES2008.txt"))
COST=0.50
ENTRY_TIMES=["09:30","10:00","10:30","11:00","11:30","12:00","12:30","13:00","13:30","14:00","14:30","15:00"]
HORIZONS=[60,120,180,9999]
HIT_HORIZONS=[30,60,90,120,180,9999]
TPS=np.array([5.,8.,10.,12.,15.,20.,25.])
MULTS=np.array([1.,1.5,2.,3.,5.,7.5,10.])
PERIODS={"DISC_2008_2016":("2008-01-01","2016-12-31"),"VAL_2017_2021":("2017-01-01","2021-12-31"),"TEST_2022_2026":("2022-01-01","2026-12-31"),"FULL":("2008-01-01","2026-12-31")}
PREV_BINS=[-9999,-20,-10,-5,0,5,10,20,9999]

def norm(s): return re.sub(r"[^a-z0-9]","",str(s).lower())

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
        z=pd.DataFrame({"ts":dt,
            "open":pd.to_numeric(ch.open,errors="coerce").astype("float32"),
            "high":pd.to_numeric(ch.high,errors="coerce").astype("float32"),
            "low":pd.to_numeric(ch.low,errors="coerce").astype("float32"),
            "close":pd.to_numeric(ch.close,errors="coerce").astype("float32")})
        chunks.append(z.dropna())
    df=pd.concat(chunks,ignore_index=True).drop_duplicates("ts").sort_values("ts").reset_index(drop=True)
    return df

def sessions(df):
    df["date"]=df.ts.dt.normalize(); df["hm"]=df.ts.dt.hour*60+df.ts.dt.minute
    r=df[(df.hm>=570)&(df.hm<960)].copy()
    by={}; rows=[]
    for d,g in r.groupby("date",sort=True):
        if len(g)<300: continue
        g=g.sort_values("ts").reset_index(drop=True)
        d=pd.Timestamp(d); by[d]=g
        rows.append((d,float(g.open.iloc[0]),float(g.high.max()),float(g.low.min()),float(g.close.iloc[-1])))
    T=pd.DataFrame(rows,columns=["date","O","H","L","C"]).set_index("date")
    T["pC"]=T.C.shift(); T["ret"]=T.C/T.pC-1
    tr=np.maximum(T.H-T.L,np.maximum((T.H-T.pC).abs(),(T.L-T.pC).abs()))
    T["atr20"]=tr.rolling(20).mean().shift()
    T["ma200"]=T.C.rolling(200).mean().shift()
    T["bull"]=T.pC>T.ma200
    T["rv20"]=T.ret.rolling(20).std().shift()*np.sqrt(252)
    T["ath_prev"]=T.C.cummax().shift(); T["dd_ath"]=T.pC/T.ath_prev-1
    T["r20"]=T.pC/T.C.shift(21)-1
    move=T.C.diff().abs(); T["eff20"]=(T.pC-T.C.shift(21)).abs()/move.shift().rolling(20).sum()
    T["trend_state"]=np.select([T.r20>0.04,T.r20<-0.04,T.eff20<0.18],["UP","DOWN","BALANCE"],default="MIXED")
    q=T.rv20.expanding(min_periods=100).quantile(.75)
    T["vol_state"]=np.where(T.rv20>q,"HIGH_VOL","NORMAL_VOL")
    return by,T

def p_mask(dates,name):
    a,b=PERIODS[name]
    return (dates>=np.datetime64(a))&(dates<=np.datetime64(b))

def first_hit_matrix(arr, thresholds, ge=True):
    n=len(arr); out=np.full((n,len(thresholds)),10**6,dtype=np.int32)
    for j,t in enumerate(thresholds):
        m=arr>=t if ge else arr>=t
        if np.any(m):
            out[:,j]=np.where(m, np.arange(n)[:,None] if False else 0, 0)[:,0] if False else out[:,j]
    return out

def build_block(by,T,etime,horizon, sl_values):
    hh=[]; ll=[]; endret=[]; dates=[]; prev=[]; bull=[]; trend=[]; vol=[]; dd=[]; atr=[]
    h,m=map(int,etime.split(":")); target=h*60+m
    for d,g in by.items():
        if d not in T.index: continue
        idx=np.flatnonzero(g.hm.to_numpy()>=target)
        if len(idx)==0: continue
        i=int(idx[0]); entry=float(g.open.iloc[i])
        e=len(g)-1 if horizon==9999 else min(len(g)-1,i+horizon-1)
        ph=g.high.to_numpy(dtype=float)[i:e+1]-entry
        pl=entry-g.low.to_numpy(dtype=float)[i:e+1]
        hh.append(ph); ll.append(pl); endret.append(float(g.close.iloc[e]-entry)); dates.append(np.datetime64(d))
        prev.append(float(g.close.iloc[i-1]-g.open.iloc[i-60]) if i>=60 else np.nan)
        f=T.loc[d]; bull.append(bool(f.bull) if pd.notna(f.bull) else False); trend.append(str(f.trend_state)); vol.append(str(f.vol_state)); dd.append(float(f.dd_ath) if pd.notna(f.dd_ath) else np.nan); atr.append(float(f.atr20) if pd.notna(f.atr20) else np.nan)
    n=len(dates)
    up=np.full((n,len(TPS)),10**6,dtype=np.int32)
    dn=np.full((n,len(sl_values)),10**6,dtype=np.int32)
    mfe=np.zeros(n); mae=np.zeros(n)
    for i,(ph,pl) in enumerate(zip(hh,ll)):
        mfe[i]=np.max(ph); mae[i]=np.max(pl)
        for j,t in enumerate(TPS):
            ix=np.flatnonzero(ph>=t)
            if len(ix): up[i,j]=int(ix[0])
        for j,s in enumerate(sl_values):
            ix=np.flatnonzero(pl>=s)
            if len(ix): dn[i,j]=int(ix[0])
    return {"dates":np.array(dates),"up":up,"dn":dn,"endret":np.array(endret),"mfe":mfe,"mae":mae,
            "prev":np.array(prev),"bull":np.array(bull,dtype=object),"trend":np.array(trend,dtype=object),
            "vol":np.array(vol,dtype=object),"dd":np.array(dd),"atr":np.array(atr)}

def payoff(block,tp_i,sl_i,tp,sl):
    u=block["up"][:,tp_i]; d=block["dn"][:,sl_i]
    # conservative same-minute -> stop
    gross=np.where((d<=u)&(d<10**6),-sl,np.where((u<d)&(u<10**6),tp,block["endret"]))
    outcome=np.where((d<=u)&(d<10**6),"SL",np.where((u<d)&(u<10**6),"TP","TIME"))
    return gross-COST,outcome

def metrics(a):
    a=np.asarray(a,float)
    if len(a)==0:return None
    win=(a>0).mean(); pos=a[a>0].sum(); neg=-a[a<0].sum()
    c=np.cumsum(a); peak=np.maximum.accumulate(np.r_[0,c]); mdd=(np.r_[0,c]-peak).min()
    return len(a),win,a.mean(),a.sum(),pos/neg if neg>0 else np.nan,float(mdd)

def main():
    df=load_raw(DATA); by,T=sessions(df)
    print("DATA",len(df),df.ts.min(),df.ts.max(),"sessions",len(T))
    T.to_csv(OUT/"daily_features.csv")
    sl_values=np.array(sorted(set(float(tp*m) for tp in TPS for m in MULTS)))
    sl_index={round(v,8):i for i,v in enumerate(sl_values)}
    cache={}
    # Build only once per time/horizon.
    for et in ENTRY_TIMES:
        for h in sorted(set(HORIZONS+HIT_HORIZONS)):
            cache[(et,h)]=build_block(by,T,et,h,sl_values)
            print("BLOCK",et,h,len(cache[(et,h)]["dates"]),flush=True)

    # Hourly target hit atlas
    hit=[]
    for et in ENTRY_TIMES:
        for h in HIT_HORIZONS:
            b=cache[(et,h)]
            for ti,tp in enumerate(TPS):
                reached=b["up"][:,ti]<10**6
                for p in PERIODS:
                    m=p_mask(b["dates"],p); n=m.sum()
                    if not n: continue
                    x=reached[m]
                    med=np.median(b["up"][m,ti][x]+1) if x.any() else np.nan
                    hit.append([p,et,h,tp,int(n),float(x.mean()),med])
    HIT=pd.DataFrame(hit,columns=["period","entry_time","horizon_min","target_pts","n","hit_rate","median_minutes_to_target"])
    HIT.to_csv(OUT/"hourly_long_hit_rate.csv",index=False)

    grid=[]
    net_cache={}
    for et in ENTRY_TIMES:
        for h in HORIZONS:
            b=cache[(et,h)]
            for ti,tp in enumerate(TPS):
                for mult in MULTS:
                    sl=float(tp*mult); si=sl_index[round(sl,8)]
                    net,out=payoff(b,ti,si,float(tp),sl)
                    net_cache[(et,h,float(tp),sl)]=(b,net,out)
                    for p in PERIODS:
                        pm=p_mask(b["dates"],p)
                        z=metrics(net[pm])
                        if z is None: continue
                        n,wr,avg,total,pf,mdd=z
                        oo=out[pm]
                        grid.append([p,et,h,tp,sl,mult,n,wr,avg,total,pf,mdd,(oo=="TP").mean(),(oo=="SL").mean(),b["mfe"][pm].mean(),b["mae"][pm].mean()])
    G=pd.DataFrame(grid,columns=["period","entry_time","horizon_min","tp_pts","sl_pts","sl_over_tp","n","win_rate","avg_net_pts","net_pts","profit_factor","maxdd_pts","tp_rate","sl_rate","avg_mfe","avg_mae"])
    G.to_csv(OUT/"inverse_rrr_grid.csv",index=False)

    D=G[(G.period=="DISC_2008_2016")&(G.n>=1200)&(G.avg_net_pts>0)&(G.profit_factor>1)].copy()
    D["score"]=D.avg_net_pts*np.minimum(D.profit_factor,2)*np.sqrt(D.n)
    top=D.sort_values("score",ascending=False).head(20)[["entry_time","horizon_min","tp_pts","sl_pts","sl_over_tp"]].reset_index(drop=True)
    fixed=[]
    for rank,c in top.iterrows():
        z=G[(G.entry_time==c.entry_time)&(G.horizon_min==c.horizon_min)&(G.tp_pts==c.tp_pts)&(G.sl_pts==c.sl_pts)].copy()
        z.insert(0,"rank_disc",rank+1); fixed.append(z)
    FIX=pd.concat(fixed,ignore_index=True) if fixed else pd.DataFrame()
    FIX.to_csv(OUT/"discovery_fixed_top20_evaluation.csv",index=False)

    prevrows=[]; regrows=[]
    for rank,c in top.iterrows():
        key=(c.entry_time,int(c.horizon_min),float(c.tp_pts),float(c.sl_pts))
        b,net,out=net_cache[key]
        for lo,hi in zip(PREV_BINS[:-1],PREV_BINS[1:]):
            cond=(b["prev"]>lo)&(b["prev"]<=hi)&np.isfinite(b["prev"])
            for p in PERIODS:
                m=cond&p_mask(b["dates"],p)
                if m.sum()<30: continue
                z=metrics(net[m])
                prevrows.append([rank+1,p,c.entry_time,int(c.horizon_min),c.tp_pts,c.sl_pts,lo,hi,*z])
        for dim in ["bull","trend","vol"]:
            vals=b[dim]
            for grp in sorted(set(vals.astype(str))):
                cond=vals.astype(str)==grp
                for p in PERIODS:
                    m=cond&p_mask(b["dates"],p)
                    if m.sum()<40: continue
                    z=metrics(net[m])
                    regrows.append([rank+1,p,c.entry_time,int(c.horizon_min),c.tp_pts,c.sl_pts,dim,grp,*z])
    pd.DataFrame(prevrows,columns=["rank_disc","period","entry_time","horizon_min","tp_pts","sl_pts","prev60_lo","prev60_hi","n","win_rate","avg_net_pts","net_pts","profit_factor","maxdd_pts"]).to_csv(OUT/"previous_hour_condition.csv",index=False)
    pd.DataFrame(regrows,columns=["rank_disc","period","entry_time","horizon_min","tp_pts","sl_pts","dimension","regime","n","win_rate","avg_net_pts","net_pts","profit_factor","maxdd_pts"]).to_csv(OUT/"fixed_top20_regime_breakdown.csv",index=False)

    # top5 year-by-year and equity
    yrows=[]; erows=[]
    bh=T.C.diff().fillna(0)
    for y,x in bh.groupby(T.index.year): yrows.append(["ES_B&H_1contract",int(y),float(x.sum())])
    cum=0.
    for d,v in bh.items(): cum+=float(v); erows.append([d,"ES_B&H_1contract",cum])
    for rank,c in top.head(5).iterrows():
        key=(c.entry_time,int(c.horizon_min),float(c.tp_pts),float(c.sl_pts)); b,net,out=net_cache[key]
        name=f"R{rank+1}_{c.entry_time}_H{int(c.horizon_min)}_TP{c.tp_pts:g}_SL{c.sl_pts:g}"
        years=pd.DatetimeIndex(b["dates"]).year
        for y in sorted(set(years)): yrows.append([name,int(y),float(net[years==y].sum())])
        cum=0.
        for d,v in zip(b["dates"],net): cum+=float(v); erows.append([pd.Timestamp(d),name,cum])
    Y=pd.DataFrame(yrows,columns=["strategy","year","net_pts"]); E=pd.DataFrame(erows,columns=["date","strategy","equity_pts"])
    Y.to_csv(OUT/"top5_yearly_points.csv",index=False); E.to_csv(OUT/"top5_equity_points.csv",index=False)

    # Charts
    def save(name):
        plt.tight_layout(); plt.savefig(OUT/name,dpi=150,bbox_inches="tight"); plt.close()
    h0=HIT[(HIT.period=="FULL")&(HIT.horizon_min==9999)].pivot(index="entry_time",columns="target_pts",values="hit_rate")
    plt.figure(figsize=(9,5)); plt.imshow(h0.values,aspect="auto",vmin=0,vmax=1); plt.xticks(range(len(h0.columns)),h0.columns); plt.yticks(range(len(h0.index)),h0.index); plt.colorbar(label="Hit rate"); plt.title("ES2008 long target hit-rate to EOD"); plt.xlabel("Target points"); plt.ylabel("Entry ET"); save("hourly_hit_rate_heatmap.png")
    g0=G[(G.period=="DISC_2008_2016")&(G.tp_pts==15)&(G.horizon_min==180)].pivot(index="entry_time",columns="sl_over_tp",values="avg_net_pts")
    plt.figure(figsize=(9,5)); plt.imshow(g0.values,aspect="auto"); plt.xticks(range(len(g0.columns)),g0.columns); plt.yticks(range(len(g0.index)),g0.index); plt.colorbar(label="Avg net pts/trade"); plt.title("Discovery TP15 / H180 inverse-RRR surface"); plt.xlabel("SL / TP"); plt.ylabel("Entry ET"); save("inverse_rrr_tp15_h180_heatmap.png")
    ep=E.pivot(index="date",columns="strategy",values="equity_pts").sort_index().ffill().fillna(0)
    plt.figure(figsize=(11,6))
    for c in ep.columns: plt.plot(ep.index,ep[c],label=c,linewidth=1.1)
    plt.legend(fontsize=7,ncol=2); plt.ylabel("Cumulative ES points"); plt.title("Discovery-fixed top5 vs ES B&H"); save("top5_equity_vs_buyhold.png")
    yp=Y.pivot(index="strategy",columns="year",values="net_pts")
    if "ES_B&H_1contract" in yp.index:
        ex=yp.drop(index="ES_B&H_1contract").subtract(yp.loc["ES_B&H_1contract"],axis=1)
        plt.figure(figsize=(12,4)); plt.imshow(ex.values,aspect="auto"); plt.xticks(range(len(ex.columns)),ex.columns,rotation=45); plt.yticks(range(len(ex.index)),ex.index,fontsize=7); plt.colorbar(label="Excess ES points"); plt.title("Year-by-year excess vs ES B&H"); save("top5_yearly_excess_heatmap.png")

    pd.DataFrame([{"source":str(DATA),"rows_1m":len(df),"sessions":len(T),"first":df.ts.min(),"last":df.ts.max(),
      "rth":"09:30-16:00 ET","cost_points_roundtrip":COST,"intrabar_rule":"same 1m TP+SL => SL first",
      "selection":"DISC 2008-2016 only; VAL 2017-2021 and TEST 2022-2026 fixed","benchmark":"continuous back-adjusted ES points, not S&P total return"}]).to_csv(OUT/"methodology.csv",index=False)
    print("DONE",flush=True)

if __name__=="__main__": main()
