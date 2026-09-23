import os
import sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import pandas as pd, numpy as np
from session_edge import *
from session_edge.data import resample
from session_edge.engine import prepare, simulate
df=pd.read_pickle(os.environ.get('ES_PKL', 'data/es1m.pkl'))
t=df.index.time
rth5=resample(df[(t>=pd.Timestamp('09:30').time())&(t<pd.Timestamp('16:00').time())],'5min')
st=RangeBreakout(tz='America/New_York',range_end='10:00',entry_end='12:00')
cfg=BacktestConfig(risk=RiskConfig(cost_per_trade=0.5,exit_time='15:55',target_mode='none'))
P=prepare(rth5,st,cfg); tr=simulate(P,cfg)
ctx={p.ctx.date:p.ctx for p in P}
g=rth5.groupby(rth5.index.date); d=pd.DataFrame({'o':g.open.first(),'c':g.close.last()})
d['prev_ret']=(d.c/d.c.shift(1)-1).shift(1); d['gap']=d.o/d.c.shift(1)-1
tr['gap_dir']=np.sign(tr.date.map(d.gap))*tr.direction
tr['prev_dir']=np.sign(tr.date.map(d.prev_ret))*tr.direction
tr['atr']=tr.date.map(lambda x: ctx[x].atr)
tr['rng_atr']=tr.risk/tr.atr
tr['wd']=pd.to_datetime(tr.date).dt.dayofweek
tr['entry_h']=pd.to_datetime(tr.entry_time).dt.strftime('%H')
def tab(k,q=None):
    key=pd.qcut(tr[k],q,duplicates='drop') if q else tr[k]
    gg=tr.groupby(key,observed=True).r
    return pd.DataFrame({'n':gg.size(),'E':gg.mean(),'t':gg.apply(lambda s:s.mean()/s.std()*np.sqrt(len(s)))}).round(3)
print('celkem n=%d E=%.3f'%(len(tr),tr.r.mean()))
for k,q in [('direction',None),('gap_dir',None),('prev_dir',None),('atr',4),('rng_atr',4),('wd',None),('entry_h',None)]:
    print('\n--',k); print(tab(k,q).to_string())
tr['year']=pd.to_datetime(tr.date).dt.year
print('\n-- rok'); print(tab('year').to_string())
