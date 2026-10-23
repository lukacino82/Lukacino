from __future__ import annotations
import os,re,warnings
from pathlib import Path
import numpy as np,pandas as pd
warnings.filterwarnings("ignore")
OUT=Path(__file__).resolve().parent/"out";OUT.mkdir(parents=True,exist_ok=True)
DATA=Path(os.environ.get("ES2008_PATH","extracted/ES2008.txt"));COST=.50
TIMES=["09:30","10:00","10:30","11:00","11:30","12:00","12:30","13:00","13:30","14:00","14:30","15:00"]
HORS=[60,120,180,9999];TPM=np.array([.10,.15,.20,.25,.33,.50,.75]);MULTS=np.array([1.,1.5,2.,3.,5.,7.5,10.])
PER={"DISC":("2008-01-01","2016-12-31"),"VAL":("2017-01-01","2021-12-31"),"TEST":("2022-01-01","2026-12-31"),"FULL":("2008-01-01","2026-12-31")}
def norm(s):return re.sub(r"[^a-z0-9]","",str(s).lower())
def pmask(d,p):a,b=PER[p];return(d>=np.datetime64(a))&(d<=np.datetime64(b))
def bl(x,e,p):
 out=np.full(len(x),None,dtype=object);x=np.asarray(x,float)
 for a,b in zip(e[:-1],e[1:]):out[(x>a)&(x<=b)]=f"{p}({a:g},{b:g}]"
 return out
def load(path):
 f=path.open("r",errors="ignore").readline();sep="\t" if "\t" in f and f.count("\t")>f.count(",") else ",";want={"date","time","open","high","low","last","close","volume","vol"};z=[]
 for c in pd.read_csv(path,sep=sep,chunksize=800000,low_memory=False,skipinitialspace=True,usecols=lambda x:norm(str(x).strip().strip("<>")) in want):
  ren={}
  for x in c.columns:
   n=norm(str(x).strip().strip("<>"))
   if n in("date","time","open","high","low"):ren[x]=n
   elif n in("last","close"):ren[x]="close"
   elif n in("volume","vol"):ren[x]="volume"
  c=c.rename(columns=ren);ts=pd.to_datetime(c.date.astype(str).str.strip()+" "+c.time.astype(str).str.strip(),errors="coerce")
  q=pd.DataFrame({"ts":ts,"open":pd.to_numeric(c.open,errors="coerce").astype("float32"),"high":pd.to_numeric(c.high,errors="coerce").astype("float32"),"low":pd.to_numeric(c.low,errors="coerce").astype("float32"),"close":pd.to_numeric(c.close,errors="coerce").astype("float32"),"volume":pd.to_numeric(c.volume,errors="coerce").fillna(0).astype("float32")});z.append(q.dropna(subset=["ts","open","high","low","close"]))
 return pd.concat(z,ignore_index=True).drop_duplicates("ts").sort_values("ts").reset_index(drop=True)
def build(df):
 df["date"]=df.ts.dt.normalize();df["hm"]=df.ts.dt.hour*60+df.ts.dt.minute;by={};rows=[]
 for d,g0 in df.groupby("date",sort=True):
  g=g0[(g0.hm>=570)&(g0.hm<960)].copy()
  if len(g)<300:continue
  g=g.sort_values("ts").reset_index(drop=True);tp=(g.high.astype(float)+g.low.astype(float)+g.close.astype(float))/3;v=g.volume.astype(float);g["vwapD"]=(tp*v).cumsum()/v.cumsum().replace(0,np.nan)
  d=pd.Timestamp(d);by[d]=g;rows.append([d,float(g.open.iloc[0]),float(g.high.max()),float(g.low.min()),float(g.close.iloc[-1])])
 T=pd.DataFrame(rows,columns=["date","O","H","L","C"]).set_index("date");T["pC"]=T.C.shift();T["ret"]=T.C/T.pC-1
 tr=np.maximum(T.H-T.L,np.maximum((T.H-T.pC).abs(),(T.L-T.pC).abs()));T["atr"]=tr.rolling(20).mean().shift();T["rv"]=T.ret.rolling(20).std().shift()*np.sqrt(252);T["ma200"]=T.C.rolling(200).mean().shift();T["bull"]=T.pC>T.ma200
 T["gap"]=(T.O-T.pC)/T.atr;T["ath"]=T.C.cummax().shift();T["dd"]=T.pC/T.ath-1;T["r20"]=T.pC/T.C.shift(21)-1;mv=T.C.diff().abs();T["eff"]=(T.pC-T.C.shift(21)).abs()/mv.shift().rolling(20).sum();T["trend"]=np.select([T.r20>.04,T.r20<-.04,T.eff<.18],["UP","DOWN","BALANCE"],default="MIXED")
 dn=(T.ret.shift()<0).astype(int);up=(T.ret.shift()>0).astype(int);T["dnst"]=dn.groupby((dn==0).cumsum()).cumsum();T["upst"]=up.groupby((up==0).cumsum()).cumsum()
 return by,T
def met(a):
 pos=a[a>0].sum();neg=-a[a<0].sum();c=np.cumsum(a);pk=np.maximum.accumulate(np.r_[0,c]);return[len(a),(a>0).mean(),a.mean(),a.sum(),pos/neg if neg>0 else np.nan,(np.r_[0,c]-pk).min()]
def main():
 df=load(DATA);by,T=build(df);states=[];paths={}
 for d,g in by.items():
  if d not in T.index or not np.isfinite(T.loc[d,"atr"]) or T.loc[d,"atr"]<=0:continue
  f=T.loc[d];atr=float(f.atr)
  for et in TIMES:
   hh,mm=map(int,et.split(":"));ix=np.flatnonzero(g.hm.to_numpy()>=hh*60+mm)
   if not len(ix):continue
   i=int(ix[0]);entry=float(g.open.iloc[i]);p60=float(g.close.iloc[i-1]-g.open.iloc[max(0,i-60)]) if i else np.nan;vw=float(g.vwapD.iloc[i-1]) if i>0 and pd.notna(g.vwapD.iloc[i-1]) else np.nan
   states.append([np.datetime64(d),et,atr,p60/atr if np.isfinite(p60) else np.nan,float(f.gap) if pd.notna(f.gap) else np.nan,float(f.dd) if pd.notna(f.dd) else np.nan,float(f.rv) if pd.notna(f.rv) else np.nan,(entry-vw)/atr if np.isfinite(vw) else np.nan,str(bool(f.bull)),str(f.trend),int(f.dnst),int(f.upst)])
   si=len(states)-1
   for h in HORS:
    e=len(g)-1 if h==9999 else min(len(g)-1,i+h-1);ph=g.high.to_numpy(dtype=float)[i:e+1]-entry;pl=entry-g.low.to_numpy(dtype=float)[i:e+1];cr=float(g.close.iloc[e]-entry);cmx=np.maximum.accumulate(ph);cmn=np.maximum.accumulate(pl)
    U=np.full(len(TPM),10**6,np.int32);D=np.full((len(TPM),len(MULTS)),10**6,np.int32)
    for ti,tm in enumerate(TPM):
     th=tm*atr;j=np.searchsorted(cmx,th);U[ti]=j if j<len(cmx) else 10**6
     for mi,mul in enumerate(MULTS):
      th2=tm*mul*atr;k=np.searchsorted(cmn,th2);D[ti,mi]=k if k<len(cmn) else 10**6
    paths[(si,h)]=(U,D,cr)
 S=pd.DataFrame(states,columns=["date","time","atr","p60a","gap","dd","rv","dvwap","bull","trend","dnst","upst"])
 S["p60_state"]=bl(S.p60a,[-1e9,-1.5,-1,-.5,0,.5,1,1.5,1e9],"p60a");S["gap_state"]=bl(S.gap,[-1e9,-1,-.5,-.25,0,.25,.5,1,1e9],"gap");S["dd_state"]=bl(S.dd,[-1,-.2,-.1,-.05,.001],"dd");S["rv_state"]=bl(S.rv,[0,.12,.2,.3,9],"rv");S["dvw_state"]=bl(S.dvwap,[-1e9,-1.5,-1,-.5,0,.5,1,1.5,1e9],"dvw");S["dn_state"]=bl(S.dnst,[-.1,.5,1.5,2.5,3.5,99],"dn");S["up_state"]=bl(S.upst,[-.1,.5,1.5,2.5,3.5,99],"up");S["bull_state"]=S.bull;S["trend_state"]=S.trend;S.to_csv(OUT/"states.csv",index=False)
 dims=["p60_state","gap_state","dd_state","rv_state","dvw_state","dn_state","up_state","bull_state","trend_state"];dates=S.date.values.astype("datetime64[ns]");rows=[]
 for et in TIMES:
  tid=S.index[S.time==et].to_numpy()
  for dim in dims:
   for state,idx0 in S.loc[tid].groupby(dim,dropna=True).groups.items():
    ids=np.asarray(list(idx0),int)
    for h in HORS:
     U=np.stack([paths[(q,h)][0] for q in ids]);D=np.stack([paths[(q,h)][1] for q in ids]);CR=np.array([paths[(q,h)][2] for q in ids]);ATR=S.loc[ids,"atr"].to_numpy()
     for ti,tm in enumerate(TPM):
      tp=tm*ATR
      for mi,mul in enumerate(MULTS):
       sl=tm*mul*ATR;u=U[:,ti];d=D[:,ti,mi];gross=np.where((d<=u)&(d<10**6),-sl,np.where((u<d)&(u<10**6),tp,CR));net=gross-COST
       for p in PER:
        q=pmask(dates[ids],p)
        if q.sum()<50:continue
        rows.append([et,dim,str(state),p,h,tm,mul,*met(net[q]),tp[q].mean(),sl[q].mean()])
 R=pd.DataFrame(rows,columns=["time","dimension","state","period","horizon","tp_atr","sl_over_tp","n","win_rate","avg_net_pts","net_pts","profit_factor","maxdd_pts","avg_tp_pts","avg_sl_pts"]);R.to_csv(OUT/"state_time_atr_grid.csv",index=False)
 D0=R[(R.period=="DISC")&(R.n>=150)&(R.avg_net_pts>0)&(R.profit_factor>1)].copy();D0["plateau"]=False
 for _,g in D0.groupby(["time","dimension","state","horizon","tp_atr"]):
  ms=sorted(g.sl_over_tp.unique());keep=set()
  for a,b in zip(ms[:-1],ms[1:]):
   ia=np.where(MULTS==a)[0];ib=np.where(MULTS==b)[0]
   if len(ia)and len(ib)and abs(int(ia[0])-int(ib[0]))==1:keep|={a,b}
  if keep:D0.loc[g[g.sl_over_tp.isin(keep)].index,"plateau"]=True
 P=D0[D0.plateau].copy();P["score"]=P.avg_net_pts*np.sqrt(P.n)*np.minimum(P.profit_factor,2);top=P.sort_values("score",ascending=False).head(100);top.to_csv(OUT/"discovery_plateau.csv",index=False)
 fixed=[]
 for rank,(_,c) in enumerate(top.iterrows(),1):
  z=R[(R.time==c.time)&(R.dimension==c.dimension)&(R.state==c.state)&(R.horizon==c.horizon)&(R.tp_atr==c.tp_atr)&(R.sl_over_tp==c.sl_over_tp)].copy();z.insert(0,"rank",rank);fixed.append(z)
 F=pd.concat(fixed,ignore_index=True) if fixed else pd.DataFrame();F.to_csv(OUT/"fixed.csv",index=False)
 st=[]
 if len(F):
  for rank,g in F.groupby("rank"):
   q={r.period:r for _,r in g.iterrows()};d=q.get("DISC");v=q.get("VAL");t=q.get("TEST");f=q.get("FULL")
   st.append([rank,d.time,d.dimension,d.state,d.horizon,d.tp_atr,d.sl_over_tp,d.n,d.avg_net_pts,d.profit_factor,v.n if v is not None else np.nan,v.avg_net_pts if v is not None else np.nan,v.profit_factor if v is not None else np.nan,t.n if t is not None else np.nan,t.avg_net_pts if t is not None else np.nan,t.profit_factor if t is not None else np.nan,f.avg_net_pts if f is not None else np.nan])
 ST=pd.DataFrame(st,columns=["rank","time","dimension","state","horizon","tp_atr","sl_over_tp","disc_n","disc_avg","disc_pf","val_n","val_avg","val_pf","test_n","test_avg","test_pf","full_avg"])
 if len(ST):ST["survive_val"]=(ST.val_avg>0)&(ST.val_pf>1);ST["all3"]=ST.survive_val&(ST.test_avg>0)&(ST.test_pf>1)
 ST.to_csv(OUT/"stability.csv",index=False)
 pd.DataFrame([{"rows":len(df),"sessions":len(T),"min_disc_n":150,"cost":COST,"selection":"scale-invariant state x fixed time x ATR payoff; DISC + adjacent SL plateau"}]).to_csv(OUT/"methodology.csv",index=False)
 print("DISC_POS",len(D0),"PLATEAU",len(P),"TOP",len(top),"VAL_SURVIVE",int(ST.survive_val.sum()) if len(ST) else 0,"ALL3",int(ST.all3.sum()) if len(ST) else 0,flush=True)
if __name__=="__main__":main()
