import os
import sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import pandas as pd, numpy as np
from dataclasses import replace
from session_edge import *
from session_edge.data import resample
from session_edge.engine import prepare, simulate
from session_edge.stats import summary
df=pd.read_pickle(os.environ.get('ES_PKL', 'data/es1m.pkl'))
t=df.index.time
rth1=df[(t>=pd.Timestamp('09:30').time())&(t<pd.Timestamp('16:00').time())]
rth5=resample(rth1,'5min')
rows=[]
def run(label,data,strat,**rk):
    cfg=BacktestConfig(risk=RiskConfig(cost_per_trade=0.5,exit_time='15:55',**rk))
    tr=simulate(prepare(data,strat,cfg),cfg); s=summary(tr)
    rows.append(dict(var=label,**{k:s[k] for k in ('trades','win_rate','expectancy_r','t_stat','profit_factor','max_drawdown_r')}))
    return tr
for rng_end,data,lab in [('09:35',rth1,'ORB5 1m'),('09:45',rth5,'ORB15'),('10:00',rth5,'ORB30'),('10:30',rth5,'ORB60')]:
    for stop_at in ('opposite','mid'):
        st=RangeBreakout(tz='America/New_York',range_end=rng_end,entry_end='12:00',stop_at=stop_at)
        for rk,rl in [(dict(rrr=2),'rrr2'),(dict(rrr=5),'rrr5'),(dict(target_mode='none'),'hold->close')]:
            run(f'{lab} stop={stop_at} {rl}',data,st,**rk)
res=pd.DataFrame(rows).set_index('var'); print(res.round(3).to_string())
res.to_csv('out/orb_deep.csv')
