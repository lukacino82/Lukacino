"""Čím se liší dny, kdy ES1 obchodoval, od ostatních dní ve stejném období?"""
import os
import numpy as np, pandas as pd
S=os.environ.get('SCRATCH','out')
df=pd.read_pickle(os.environ.get('ES_PKL',f'{S}/data/es1m.pkl')); tr=pd.read_pickle(f'{S}/es1_trades.pkl')
t=df.index.time
rth=df[(t>=pd.Timestamp('09:30').time())&(t<pd.Timestamp('16:00').time())]
g=rth.groupby(rth.index.date)
d=pd.DataFrame({'o':g.open.first(),'c':g.close.last(),'h':g.high.max(),'l':g.low.min()}); d.index=pd.to_datetime(d.index)
f15=rth[rth.index.time<pd.Timestamp('09:45').time()].groupby(rth.index.date[rth.index.time<pd.Timestamp('09:45').time()]).close.last(); f15.index=pd.to_datetime(f15.index)
d['gap']=d.o-d.c.shift(1); d['prev_ret']=(d.c-d.o).shift(1); d['prev_cc']=d.c.diff().shift(1)
d['first15']=f15-d.o; d['above_ma20']=(d.c.shift(1)>d.c.rolling(20).mean().shift(1)).astype(int)
d['above_ma50']=(d.c.shift(1)>d.c.rolling(50).mean().shift(1)).astype(int)
d['dow']=d.index.dayofweek
d['day_ret']=d.c-d.o
m=(d.index>=tr.entry.min().normalize())&(d.index<=tr.exit.max().normalize()); p=d[m].copy()
p['traded']=p.index.isin(pd.to_datetime(tr.entry.dt.date)).astype(int)
print('dní',len(p),'obchodováno',p.traded.sum())
print(p.groupby('traded')[['gap','first15','prev_ret','prev_cc','above_ma20','above_ma50','day_ret']].mean().round(2).T.to_string())
print('\nden v týdnu:',p.groupby('dow').traded.mean().round(2).to_dict())
for k in ('gap','first15','prev_cc'):
    q=pd.qcut(p[k],5); print(k, p.groupby(q,observed=True).traded.mean().round(2).to_dict())
