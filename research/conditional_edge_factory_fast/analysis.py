from __future__ import annotations
import os,re,warnings
from pathlib import Path
import numpy as np,pandas as pd
warnings.filterwarnings("ignore")

OUT=Path(__file__).resolve().parent/"out"; OUT.mkdir(parents=True,exist_ok=True)
DATA=Path(os.environ.get("ES2008_PATH","extracted/ES2008.txt"))
COST=.50
TIMES=["09:30","10:00","10:30","11:00","11:30","12:00","12:30","13:00","13:30","14:00","14:30","15:00"]
HORS=[60,120,180,9999]; TPS=np.array([5.,8.,10.,12.,15.,20.,25.]); MULTS=np.array([1.,1.5,2.,3.,5.,7.5,10.])
SLV=np.array(sorted(set(float(t*m) for t in TPS for m in MULTS)))
SLIX={round(x,8):i for i,x in enumerate(SLV)}
PER={"DISC":("2008-01-01","2016-12-31"),"VAL":("2017-01-01","2021-12-31"),"TEST":("2022-01-01","2026-12-31"),"FULL":("2008-01-01","2026-12-31")}

def norm(s): return re.sub(r"[^a-z0-9]","",str(s).lower())
def maskp(d,p):
    a,b=PER[p]; return (d>=np.datetime64(a))&(d<=np.datetime64(b))
def binlab(x,edges,p):
    out=np.full(len(x),None,dtype=object)
    x=np.asarray(x,float)
    for a,b in zip(edges[:-1],edges[1:]): out[(x>a)&(x<=b)]=f"{p}({a:g},{b:g}]"
    return out

def load(path):
    first=path.open("r",errors="ignore").readline(); sep="\t" if "\t" in first and first.count("\t")>first.count(",") else ","
    wanted={"date","time","open","high","low","last","close","volume","vol"}; z=[]
    for c in pd.read_csv(path,sep=sep,chunksize=800000,low_memory=False,skipinitialspace=True,usecols=lambda x:norm(str(x).strip().strip("<>")) in wanted):
        ren={}
        for x in c.columns:
            n=norm(str(x).strip().strip("<>"))
            if n in ("date","time","open","high","low"):ren[x]=n
            elif n in ("last","close"):ren[x]="close"
            elif n in ("volume","vol"):ren[x]="volume"
        c=c.rename(columns=ren); ts=pd.to_datetime(c.date.astype(str).str.strip()+" "+c.time.astype(str).str.strip(),errors="coerce")
        q=pd.DataFrame({"ts":ts,"open":pd.to_numeric(c.open,errors="coerce").astype("float32"),"high":pd.to_numeric(c.high,errors="coerce").astype("float32"),"low":pd.to_numeric(c.low,errors="coerce").astype("float32"),"close":pd.to_numeric(c.close,errors="coerce").astype("float32"),"volume":pd.to_numeric(c.volume,errors="coerce").fillna(0).astype("float32")})
        z.append(q.dropna(subset=["ts","open","high","low","close"]))
    return pd.concat(z,ignore_index=True).drop_duplicates("ts").sort_values("ts").reset_index(drop=True)

def build(df):
    df["date"]=df.ts.dt.normalize();df["hm"]=df.ts.dt.hour*60+df.ts.dt.minute
    by={};rows=[]
    for d,g0 in df.groupby("date",sort=True):
        g=g0[(g0.hm>=570)&(g0.hm<960)].copy()
        if len(g)<300:continue
        g=g.sort_values("ts").reset_index(drop=True);tp=(g.high.astype(float)+g.low.astype(float)+g.close.astype(float))/3;v=g.volume.astype(float);den=v.cumsum().replace(0,np.nan);g["vwapD"]=(tp*v).cumsum()/den
        d=pd.Timestamp(d);by[d]=g;rows.append([d,float(g.open.iloc[0]),float(g.high.max()),float(g.low.min()),float(g.close.iloc[-1]),float(g.volume.sum())])
    T=pd.DataFrame(rows,columns=["date","O","H","L","C","Vol"]).set_index("date");T["pC"]=T.C.shift();T["ret"]=T.C/T.pC-1
    tr=np.maximum(T.H-T.L,np.maximum((T.H-T.pC).abs(),(T.L-T.pC).abs()));T["atr20"]=tr.rolling(20).mean().shift();T["rv20"]=T.ret.rolling(20).std().shift()*np.sqrt(252);T["ma200"]=T.C.rolling(200).mean().shift();T["bull"]=T.pC>T.ma200
    T["gap_atr"]=(T.O-T.pC)/T.atr20;T["ath"]=T.C.cummax().shift();T["dd"]=T.pC/T.ath-1;T["r20"]=T.pC/T.C.shift(21)-1
    mv=T.C.diff().abs();T["eff20"]=(T.pC-T.C.shift(21)).abs()/mv.shift().rolling(20).sum();T["trend"]=np.select([T.r20>.04,T.r20<-.04,T.eff20<.18],["UP","DOWN","BALANCE"],default="MIXED")
    dn=(T.ret.shift()<0).astype(int);up=(T.ret.shift()>0).astype(int);T["dnst"]=dn.groupby((dn==0).cumsum()).cumsum();T["upst"]=up.groupby((up==0).cumsum()).cumsum()
    return by,T

def met(a):
    if len(a)==0:return [0,np.nan,np.nan,np.nan,np.nan,np.nan]
    pos=a[a>0].sum();neg=-a[a<0].sum();c=np.cumsum(a);pk=np.maximum.accumulate(np.r_[0,c]);return [len(a),(a>0).mean(),a.mean(),a.sum(),pos/neg if neg>0 else np.nan,(np.r_[0,c]-pk).min()]

def main():
    df=load(DATA);by,T=build(df);states=[]; pathdata={}
    for d,g in by.items():
      if d not in T.index:continue
      f=T.loc[d]
      for ti,et in enumerate(TIMES):
        hh,mm=map(int,et.split(":"));ix=np.flatnonzero(g.hm.to_numpy()>=hh*60+mm)
        if not len(ix):continue
        i=int(ix[0]);entry=float(g.open.iloc[i]);atr=float(f.atr20) if pd.notna(f.atr20) else np.nan;vw=float(g.vwapD.iloc[i-1]) if i>0 and pd.notna(g.vwapD.iloc[i-1]) else np.nan
        p60=float(g.close.iloc[i-1]-g.open.iloc[max(0,i-60)]) if i else np.nan
        states.append([np.datetime64(d),et,ti,p60,p60/atr if np.isfinite(atr) and atr>0 else np.nan,str(bool(f.bull)) if pd.notna(f.bull) else None,str(f.trend),float(f.rv20) if pd.notna(f.rv20) else np.nan,float(f.dd) if pd.notna(f.dd) else np.nan,float(f.gap_atr) if pd.notna(f.gap_atr) else np.nan,(entry-vw)/atr if np.isfinite(atr) and atr>0 and np.isfinite(vw) else np.nan,int(f.dnst),int(f.upst)])
        si=len(states)-1
        for h in HORS:
          e=len(g)-1 if h==9999 else min(len(g)-1,i+h-1);ph=g.high.to_numpy(dtype=float)[i:e+1]-entry;pl=entry-g.low.to_numpy(dtype=float)[i:e+1];cr=float(g.close.iloc[e]-entry)
          U=np.full(len(TPS),10**6,np.int32);D=np.full(len(SLV),10**6,np.int32)
          for j,t in enumerate(TPS):
            x=np.flatnonzero(ph>=t)
            if len(x):U[j]=x[0]
          for j,s in enumerate(SLV):
            x=np.flatnonzero(pl>=s)
            if len(x):D[j]=x[0]
          pathdata[(si,h)]=(U,D,cr,float(ph.max()),float(pl.max()))
    S=pd.DataFrame(states,columns=["date","time","time_ix","prev60","prev60_atr","bull","trend","rv20","dd","gap_atr","dvwap_atr","dnst","upst"])
    S["prev60_pts_state"]=binlab(S.prev60,[-1e9,-20,-10,-5,0,5,10,20,1e9],"p60")
    S["prev60_atr_state"]=binlab(S.prev60_atr,[-1e9,-1.5,-1,-.5,0,.5,1,1.5,1e9],"p60a")
    S["gap_state"]=binlab(S.gap_atr,[-1e9,-1,-.5,-.25,0,.25,.5,1,1e9],"gap")
    S["dd_state"]=binlab(S.dd,[-1,-.20,-.10,-.05,0.001],"dd")
    S["rv_state"]=binlab(S.rv20,[0,.12,.20,.30,9],"rv")
    S["dvwap_state"]=binlab(S.dvwap_atr,[-1e9,-1.5,-1,-.5,0,.5,1,1.5,1e9],"dvw")
    S["dn_state"]=binlab(S.dnst.astype(float),[-.1,.5,1.5,2.5,3.5,99],"dn")
    S["up_state"]=binlab(S.upst.astype(float),[-.1,.5,1.5,2.5,3.5,99],"up")
    S["bull_state"]=S.bull;S["trend_state"]=S.trend
    S.to_csv(OUT/"entry_states.csv",index=False)
    dims=["time","prev60_pts_state","prev60_atr_state","gap_state","dd_state","rv_state","dvwap_state","dn_state","up_state","bull_state","trend_state"]
    dates=S.date.values.astype("datetime64[ns]")
    dist=[];rr=[]
    for dim in dims:
      for state,idx0 in S.groupby(dim,dropna=True).groups.items():
        ids=np.asarray(list(idx0),int)
        for h in HORS:
          U=np.stack([pathdata[(q,h)][0] for q in ids]);D=np.stack([pathdata[(q,h)][1] for q in ids]);CR=np.array([pathdata[(q,h)][2] for q in ids]);MFE=np.array([pathdata[(q,h)][3] for q in ids]);MAE=np.array([pathdata[(q,h)][4] for q in ids])
          for p in PER:
            pm=maskp(dates[ids],p)
            if pm.sum()>=80:dist.append([dim,str(state),p,h,int(pm.sum()),MFE[pm].mean(),np.median(MFE[pm]),MAE[pm].mean(),np.median(MAE[pm]),CR[pm].mean(),*[(MFE[pm]>=t).mean() for t in TPS]])
          for tj,tp in enumerate(TPS):
            for mult in MULTS:
              sl=float(tp*mult);dj=SLIX[round(sl,8)];u=U[:,tj];d=D[:,dj];gross=np.where((d<=u)&(d<10**6),-sl,np.where((u<d)&(u<10**6),tp,CR));net=gross-COST
              for p in PER:
                pm=maskp(dates[ids],p)
                if pm.sum()<80:continue
                rr.append([dim,str(state),p,h,tp,sl,mult,*met(net[pm])])
    dc=["dimension","state","period","horizon_min","n","mean_mfe","median_mfe","mean_mae","median_mae","mean_close_ret"]+[f"p_mfe_ge_{int(t)}" for t in TPS]
    pd.DataFrame(dist,columns=dc).to_csv(OUT/"conditional_excursions.csv",index=False)
    rc=["dimension","state","period","horizon_min","tp_pts","sl_pts","sl_over_tp","n","win_rate","avg_net_pts","net_pts","profit_factor","maxdd_pts"]
    R=pd.DataFrame(rr,columns=rc);R.to_csv(OUT/"conditional_rrr_grid.csv",index=False)
    D0=R[(R.period=="DISC")&(R.n>=250)&(R.avg_net_pts>0)&(R.profit_factor>1)].copy();D0["plateau"]=False
    for _,g in D0.groupby(["dimension","state","horizon_min","tp_pts"]):
      ms=sorted(g.sl_over_tp.unique());keep=set()
      for a,b in zip(ms[:-1],ms[1:]):
        ia=np.where(MULTS==a)[0];ib=np.where(MULTS==b)[0]
        if len(ia) and len(ib) and abs(int(ia[0])-int(ib[0]))==1:keep|={a,b}
      if keep:D0.loc[g[g.sl_over_tp.isin(keep)].index,"plateau"]=True
    P=D0[D0.plateau].copy();P["score"]=P.avg_net_pts*np.sqrt(P.n)*np.minimum(P.profit_factor,2);top=P.sort_values("score",ascending=False).head(50);top.to_csv(OUT/"discovery_candidates_plateau.csv",index=False)
    fixed=[]
    for rank,(_,c) in enumerate(top.iterrows(),1):
      z=R[(R.dimension==c.dimension)&(R.state==c.state)&(R.horizon_min==c.horizon_min)&(R.tp_pts==c.tp_pts)&(R.sl_pts==c.sl_pts)&(R.sl_over_tp==c.sl_over_tp)].copy();z.insert(0,"rank_disc",rank);fixed.append(z)
    F=pd.concat(fixed,ignore_index=True) if fixed else pd.DataFrame();F.to_csv(OUT/"fixed_evaluation.csv",index=False)
    st=[]
    if len(F):
      for rank,g in F.groupby("rank_disc"):
        q={r.period:r for _,r in g.iterrows()};d=q.get("DISC");v=q.get("VAL");t=q.get("TEST");f=q.get("FULL")
        st.append([rank,d.dimension,d.state,d.horizon_min,d.tp_pts,d.sl_pts,d.n,d.avg_net_pts,d.profit_factor,
                   v.n if v is not None else np.nan,v.avg_net_pts if v is not None else np.nan,v.profit_factor if v is not None else np.nan,
                   t.n if t is not None else np.nan,t.avg_net_pts if t is not None else np.nan,t.profit_factor if t is not None else np.nan,
                   f.avg_net_pts if f is not None else np.nan])
    ST=pd.DataFrame(st,columns=["rank","dimension","state","horizon","tp","sl","disc_n","disc_avg","disc_pf","val_n","val_avg","val_pf","test_n","test_avg","test_pf","full_avg"])
    if len(ST):ST["survive_val"]=(ST.val_avg>0)&(ST.val_pf>1);ST["all3"]=(ST.survive_val)&(ST.test_avg>0)&(ST.test_pf>1)
    ST.to_csv(OUT/"stability.csv",index=False)
    pd.DataFrame([{"rows":len(df),"sessions":len(T),"cost":COST,"selection":"DISC only + adjacent SL plateau","pseudo_oos":"2022-2026 previously viewed"}]).to_csv(OUT/"methodology.csv",index=False)
    print("DISC_POS",len(D0),"PLATEAU",len(P),"TOP",len(top),"VAL_SURVIVE",int(ST.survive_val.sum()) if len(ST) else 0,"ALL3",int(ST.all3.sum()) if len(ST) else 0,flush=True)
if __name__=="__main__":main()
