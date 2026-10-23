from __future__ import annotations
import os,re,warnings
from pathlib import Path
import numpy as np,pandas as pd
warnings.filterwarnings("ignore")
OUT=Path(__file__).resolve().parent/"out"; OUT.mkdir(parents=True,exist_ok=True)
DATA=Path(os.environ.get("ES2008_PATH","extracted/ES2008.txt"))
COST=.50
TIMES=["09:30","10:00","10:30","11:00","11:30","12:00","12:30","13:00","13:30","14:00","14:30","15:00"]
HORS=[60,120,180,9999]; TPM=np.array([.10,.15,.20,.25,.33,.50,.75]); MULTS=np.array([1.,1.5,2.,3.,5.,7.5,10.])
PER={"DISC":("2008-01-01","2016-12-31"),"VAL":("2017-01-01","2021-12-31"),"TEST":("2022-01-01","2026-12-31"),"FULL":("2008-01-01","2026-12-31")}
def norm(s):return re.sub(r"[^a-z0-9]","",str(s).lower())
def pmask(d,p):a,b=PER[p];return(d>=np.datetime64(a))&(d<=np.datetime64(b))
def load(path):
 f=path.open("r",errors="ignore").readline();sep="\t" if "\t" in f and f.count("\t")>f.count(",") else ",";want={"date","time","open","high","low","last","close","volume","vol"};out=[]
 for c in pd.read_csv(path,sep=sep,chunksize=800000,low_memory=False,skipinitialspace=True,usecols=lambda x:norm(str(x).strip().strip("<>")) in want):
  ren={}
  for x in c.columns:
   n=norm(str(x).strip().strip("<>"))
   if n in("date","time","open","high","low"):ren[x]=n
   elif n in("last","close"):ren[x]="close"
   elif n in("volume","vol"):ren[x]="volume"
  c=c.rename(columns=ren);ts=pd.to_datetime(c.date.astype(str).str.strip()+" "+c.time.astype(str).str.strip(),errors="coerce")
  q=pd.DataFrame({"ts":ts,"open":pd.to_numeric(c.open,errors="coerce").astype("float32"),"high":pd.to_numeric(c.high,errors="coerce").astype("float32"),"low":pd.to_numeric(c.low,errors="coerce").astype("float32"),"close":pd.to_numeric(c.close,errors="coerce").astype("float32")});out.append(q.dropna())
 return pd.concat(out,ignore_index=True).drop_duplicates("ts").sort_values("ts").reset_index(drop=True)
def build(df):
 df["date"]=df.ts.dt.normalize();df["hm"]=df.ts.dt.hour*60+df.ts.dt.minute;by={};rows=[]
 for d,g in df.groupby("date",sort=True):
  g=g[(g.hm>=570)&(g.hm<960)].copy()
  if len(g)<300:continue
  g=g.sort_values("ts").reset_index(drop=True);d=pd.Timestamp(d);by[d]=g;rows.append([d,float(g.open.iloc[0]),float(g.high.max()),float(g.low.min()),float(g.close.iloc[-1])])
 T=pd.DataFrame(rows,columns=["date","O","H","L","C"]).set_index("date");T["pC"]=T.C.shift();T["ret"]=T.C/T.pC-1;tr=np.maximum(T.H-T.L,np.maximum((T.H-T.pC).abs(),(T.L-T.pC).abs()));T["atr20"]=tr.rolling(20).mean().shift();return by,T
def met(a):
 pos=a[a>0].sum();neg=-a[a<0].sum();c=np.cumsum(a);pk=np.maximum.accumulate(np.r_[0,c]);return[len(a),(a>0).mean(),a.mean(),a.sum(),pos/neg if neg>0 else np.nan,(np.r_[0,c]-pk).min()]
def main():
 df=load(DATA);by,T=build(df);blocks={}
 for et in TIMES:
  dates=[];atrs=[];paths=[]
  hh,mm=map(int,et.split(":"));target=hh*60+mm
  for d,g in by.items():
   if d not in T.index or not np.isfinite(T.loc[d,"atr20"]) or T.loc[d,"atr20"]<=0:continue
   ix=np.flatnonzero(g.hm.to_numpy()>=target)
   if not len(ix):continue
   i=int(ix[0]);entry=float(g.open.iloc[i]);atr=float(T.loc[d,"atr20"]);dates.append(np.datetime64(d));atrs.append(atr)
   pdict={}
   for h in HORS:
    e=len(g)-1 if h==9999 else min(len(g)-1,i+h-1);ph=g.high.to_numpy(dtype=float)[i:e+1]-entry;pl=entry-g.low.to_numpy(dtype=float)[i:e+1];cr=float(g.close.iloc[e]-entry)
    cmx=np.maximum.accumulate(ph);cmn=np.maximum.accumulate(pl)
    U=[];D=[]
    for tm in TPM:
     th=tm*atr;j=np.searchsorted(cmx,th,side="left");U.append(j if j<len(cmx) else 10**6)
    for tm in TPM:
     for mlt in MULTS:
      th=tm*mlt*atr;j=np.searchsorted(cmn,th,side="left");D.append(j if j<len(cmn) else 10**6)
    pdict[h]=(np.array(U,np.int32),np.array(D,np.int32),cr)
   paths.append(pdict)
  blocks[et]=(np.array(dates),np.array(atrs),paths)
 grid=[]
 for et,(dates,atrs,paths) in blocks.items():
  for h in HORS:
   U=np.stack([x[h][0] for x in paths]);D=np.stack([x[h][1] for x in paths]);CR=np.array([x[h][2] for x in paths])
   for ti,tm in enumerate(TPM):
    for mi,mult in enumerate(MULTS):
     di=ti*len(MULTS)+mi;tp=tm*atrs;sl=tm*mult*atrs;u=U[:,ti];d=D[:,di];gross=np.where((d<=u)&(d<10**6),-sl,np.where((u<d)&(u<10**6),tp,CR));net=gross-COST
     for p in PER:
      q=pmask(dates,p)
      if q.sum()<100:continue
      n,wr,av,total,pf,mdd=met(net[q]);grid.append([p,et,h,tm,mult,n,wr,av,total,pf,mdd,np.mean(tp[q]),np.mean(sl[q])])
 G=pd.DataFrame(grid,columns=["period","entry_time","horizon_min","tp_atr","sl_over_tp","n","win_rate","avg_net_pts","net_pts","profit_factor","maxdd_pts","avg_tp_pts","avg_sl_pts"]);G.to_csv(OUT/"atr_rrr_grid.csv",index=False)
 D=G[(G.period=="DISC")&(G.avg_net_pts>0)&(G.profit_factor>1)].copy();D["plateau"]=False
 for _,g in D.groupby(["entry_time","horizon_min","tp_atr"]):
  ms=sorted(g.sl_over_tp.unique());keep=set()
  for a,b in zip(ms[:-1],ms[1:]):
   ia=np.where(MULTS==a)[0];ib=np.where(MULTS==b)[0]
   if len(ia)and len(ib)and abs(int(ia[0])-int(ib[0]))==1:keep|={a,b}
  if keep:D.loc[g[g.sl_over_tp.isin(keep)].index,"plateau"]=True
 P=D[D.plateau].copy();P["score"]=P.avg_net_pts*np.sqrt(P.n)*np.minimum(P.profit_factor,2);top=P.sort_values("score",ascending=False).head(30);top.to_csv(OUT/"discovery_plateau.csv",index=False)
 fixed=[]
 for rank,(_,c) in enumerate(top.iterrows(),1):
  z=G[(G.entry_time==c.entry_time)&(G.horizon_min==c.horizon_min)&(G.tp_atr==c.tp_atr)&(G.sl_over_tp==c.sl_over_tp)].copy();z.insert(0,"rank_disc",rank);fixed.append(z)
 F=pd.concat(fixed,ignore_index=True) if fixed else pd.DataFrame();F.to_csv(OUT/"fixed_evaluation.csv",index=False)
 st=[]
 if len(F):
  for rank,g in F.groupby("rank_disc"):
   q={r.period:r for _,r in g.iterrows()};d=q.get("DISC");v=q.get("VAL");t=q.get("TEST");f=q.get("FULL")
   st.append([rank,d.entry_time,d.horizon_min,d.tp_atr,d.sl_over_tp,d.n,d.avg_net_pts,d.profit_factor,v.avg_net_pts if v is not None else np.nan,v.profit_factor if v is not None else np.nan,t.avg_net_pts if t is not None else np.nan,t.profit_factor if t is not None else np.nan,f.avg_net_pts if f is not None else np.nan])
 ST=pd.DataFrame(st,columns=["rank","time","horizon","tp_atr","sl_over_tp","disc_n","disc_avg","disc_pf","val_avg","val_pf","test_avg","test_pf","full_avg"])
 if len(ST):ST["survive_val"]=(ST.val_avg>0)&(ST.val_pf>1);ST["all3"]=(ST.survive_val)&(ST.test_avg>0)&(ST.test_pf>1)
 ST.to_csv(OUT/"stability.csv",index=False)
 pd.DataFrame([{"rows":len(df),"sessions":len(T),"targets_atr":"0.10,0.15,0.20,0.25,0.33,0.50,0.75","cost":COST,"selection":"DISC + adjacent SL plateau"}]).to_csv(OUT/"methodology.csv",index=False)
 print("DISC_POS",len(D),"PLATEAU",len(P),"VAL_SURVIVE",int(ST.survive_val.sum()) if len(ST) else 0,"ALL3",int(ST.all3.sum()) if len(ST) else 0,flush=True)
if __name__=="__main__":main()
