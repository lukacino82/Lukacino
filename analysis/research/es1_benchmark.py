"""Nulová hypotéza pro ES1: long v náhodném čase 09:45–11:30, SL 10 b., TP 30 b.,
výstup 15:56 – kolik vydělá 'jen být long' se stejnými závorkami?"""
import os
import numpy as np, pandas as pd
S=os.environ.get('SCRATCH','out')
df=pd.read_pickle(os.environ.get('ES_PKL',f'{S}/data/es1m.pkl'))
tr=pd.read_pickle(f'{S}/es1_trades.pkl')
t=df.index.time
rth=df[(t>=pd.Timestamp('09:30').time())&(t<pd.Timestamp('15:56').time())]
SL,TP=10.0,30.0
rows=[]
for d,g in rth.groupby(rth.index.date):
    if len(g)<300: continue
    o,h,l,c=(g[k].values for k in ('open','high','low','close')); tm=g.index.time
    starts=np.flatnonzero((tm>=pd.Timestamp('09:45').time())&(tm<=pd.Timestamp('11:30').time()))
    res=np.empty(len(starts))
    for i,s in enumerate(starts):
        e=o[s]; hs=h[s:]>=e+TP; ls=l[s:]<=e-SL
        fs=np.argmax(ls) if ls.any() else 10**9; ft=np.argmax(hs) if hs.any() else 10**9
        res[i]=-SL if fs<=ft and fs<10**9 else (TP if ft<10**9 else c[-1]-e)
    rows.append((pd.Timestamp(d),res))
days=pd.Series({d:r for d,r in rows})
per_day=days.map(np.mean)  # průměr náhodného vstupu v daný den
print('dní',len(days))
yr=per_day.groupby(per_day.index.year).agg(['mean','count']); print('průměr bodů/obchod náhodný long (SL10/TP30):'); print(yr.round(2).to_string())
# stejné období jako ES1 a stejný počet obchodů
m=(per_day.index>=tr.entry.min().normalize())&(per_day.index<=tr.exit.max().normalize())
pdays=days[m]; rng=np.random.default_rng(0)
real=tr.pts.mean()
sims=[]
for _ in range(20000):
    idx=rng.integers(0,len(pdays),len(tr)); 
    sims.append(np.mean([pdays.iloc[i][rng.integers(0,len(pdays.iloc[i]))] for i in idx]))
sims=np.array(sims)
print(f'\nES1 skutečnost: {real:.2f} b./obchod | náhodný long ve stejném období: průměr {sims.mean():.2f}, 95% {np.quantile(sims,0.95):.2f}, p={((sims>=real).mean()):.3f}')
# ve stejné dny, jako obchodoval systém (výběr dne vs. výběr času)
same=[days.get(pd.Timestamp(e.date())) for e in tr.entry]
same=[s for s in same if s is not None]
print(f'náhodný čas vstupu ve STEJNÉ dny jako ES1: {np.mean([s.mean() for s in same]):.2f} b./obchod (n={len(same)})')
print('podíl dní v období, kdy ES1 obchodoval: %.2f'%(len(tr)/m.sum()))
per_day.to_frame('rand_pts').to_csv(f'{S}/es1_random_daily.csv')
