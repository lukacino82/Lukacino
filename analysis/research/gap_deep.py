import os
import sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import pandas as pd, numpy as np
from session_edge import *
from session_edge.data import resample
from session_edge.engine import prepare, simulate
from session_edge.stats import summary
df=pd.read_pickle(os.environ.get('ES_PKL', 'data/es1m.pkl'))
t=df.index.time
rth5=resample(df[(t>=pd.Timestamp('09:30').time())&(t<pd.Timestamp('16:00').time())],'5min')
def T(s): return s.mean()/s.std()*np.sqrt(len(s))
rows=[]
for mn in (0.1,0.15,0.2,0.25,0.3,0.4):
    for mx in (0.8,1.5):
        for ce in ('09:45','10:00','10:15'):
            st=GapFade(tz='America/New_York',min_gap_atr=mn,max_gap_atr=mx,confirm_end=ce)
            for rrr in (1.5,2.0):
                cfg=BacktestConfig(risk=RiskConfig(cost_per_trade=0.5,exit_time='15:55',rrr=rrr))
                tr=simulate(prepare(rth5,st,cfg),cfg)
                rows.append(dict(min=mn,max=mx,confirm=ce,rrr=rrr,n=len(tr),E=tr.r.mean(),t=T(tr.r)))
res=pd.DataFrame(rows); print(res.pivot_table(index=['min','max'],columns=['confirm','rrr'],values='t').round(2).to_string())
print(); print(res.pivot_table(index=['min','max'],columns=['confirm','rrr'],values='E').round(3).to_string())
print(); print(res.pivot_table(index=['min','max'],columns=['confirm'],values='n',aggfunc='first').to_string())
# detail base variant
st=GapFade(tz='America/New_York',min_gap_atr=0.2); cfg=BacktestConfig(risk=RiskConfig(cost_per_trade=0.5,exit_time='15:55',rrr=2.0))
tr=simulate(prepare(rth5,st,cfg),cfg); tr['y']=pd.to_datetime(tr.date).dt.year
print('\nbase: n',len(tr),'E %.3f t %.2f'%(tr.r.mean(),T(tr.r)))
for k in ('direction','y','exit_reason'):
    gg=tr.groupby(k).r; print(pd.DataFrame({'n':gg.size(),'E':gg.mean(),'t':gg.apply(T)}).round(3).to_string())
print('median risk pts %.2f, cost share R %.3f'%(tr.risk.median(),(0.5/tr.risk).mean()))
for c in (0.25,0.5,1.0,1.5):
    cfg=BacktestConfig(risk=RiskConfig(cost_per_trade=c,exit_time='15:55',rrr=2.0)); x=simulate(prepare(rth5,st,cfg),cfg)
    print('cost',c,'E %.3f t %.2f'%(x.r.mean(),T(x.r)))
tr.to_csv('out/gap_trades.csv',index=False)
