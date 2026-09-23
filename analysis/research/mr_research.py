import os
import pandas as pd, numpy as np
df=pd.read_pickle(os.environ.get('ES_PKL', 'data/es1m.pkl'))
t=df.index.time
rth=df[(t>=pd.Timestamp('09:30').time())&(t<pd.Timestamp('16:00').time())]
c5=rth.close.resample('5min').last().dropna()
day=pd.Series(c5.index.date,index=c5.index)
# denní vol: ATR-like z předchozích 14 dní (RTH range) v bodech
g=rth.groupby(rth.index.date); rng=(g.high.max()-g.low.min()); atr=rng.rolling(14).mean().shift(1)
atr5=pd.Series(day.map(atr).values,index=c5.index)
# VWAP
tp=(rth.high+rth.low+rth.close)/3; pv=(tp*rth.volume).groupby(rth.index.date).cumsum(); vv=rth.volume.groupby(rth.index.date).cumsum()
vwap=(pv/vv).resample('5min').last().reindex(c5.index)
op=rth.open.groupby(rth.index.date).transform('first').resample('5min').last().reindex(c5.index)
COST=0.5
def tstat(x): x=pd.Series(x).dropna(); return x.mean()/x.std()*np.sqrt(len(x)) if len(x)>2 else np.nan
out=[]
tod=pd.Series(c5.index.time,index=c5.index)
for look in (30,60,120):
    for hold in (30,60,'close'):
        L=look//5
        past=c5-c5.groupby(day).shift(L)
        if hold=='close':
            fut=c5.groupby(day).transform('last')-c5
        else:
            fut=c5.groupby(day).shift(-hold//5)-c5
        z=past/atr5
        m=(tod>=pd.Timestamp('10:00').time())&(tod<=pd.Timestamp('15:00').time())&(tod.apply(lambda x:x.minute%30==0))
        x=pd.DataFrame({'z':z,'f':fut,'atr':atr5})[m].dropna()
        for thr in (0.15,0.25,0.35):
            s=x[abs(x.z)>thr]; pnl=-np.sign(s.z)*s.f-COST
            out.append(dict(look=look,hold=hold,thr=thr,n=len(s),pts=pnl.mean(),t=tstat(pnl),
                            win=(pnl>0).mean(),per_atr=(pnl/s.atr).mean()*100))
res=pd.DataFrame(out); print(res.round(3).to_string())
# vwap deviation fade
print('\n== fade odchylky od VWAP (v ATR), výstup 60 min / close')
dev=(c5-vwap)/atr5
for hold in (60,'close'):
    fut=(c5.groupby(day).transform('last')-c5) if hold=='close' else c5.groupby(day).shift(-12)-c5
    m=(tod>=pd.Timestamp('10:30').time())&(tod<=pd.Timestamp('15:00').time())&(tod.apply(lambda x:x.minute%30==0))
    x=pd.DataFrame({'d':dev,'f':fut})[m].dropna()
    for thr in (0.2,0.3,0.4,0.5):
        s=x[abs(x.d)>thr]; pnl=-np.sign(s.d)*s.f-COST
        print(hold,thr,len(s),round(pnl.mean(),3),round(tstat(pnl),2), 'yearly t:', {y:round(tstat(v),1) for y,v in pnl.groupby(pnl.index.year)})
