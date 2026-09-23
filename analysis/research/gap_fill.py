import os
import sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import pandas as pd, numpy as np
from session_edge import *
from session_edge.data import resample
from session_edge.engine import prepare, simulate
from session_edge.validation import validate
df=pd.read_pickle(os.environ.get('ES_PKL', 'data/es1m.pkl'))
t=df.index.time
rth5=resample(df[(t>=pd.Timestamp('09:30').time())&(t<pd.Timestamp('16:00').time())],'5min')
def T(s): return s.mean()/s.std()*np.sqrt(len(s))
for ff in (0.5,0.75,1.0):
    for mode in ('strategy',):
        st=GapFade(tz='America/New_York',min_gap_atr=0.2,fill_fraction=ff)
        cfg=BacktestConfig(risk=RiskConfig(cost_per_trade=0.5,exit_time='15:55',target_mode=mode,rrr=2.0))
        tr=simulate(prepare(rth5,st,cfg),cfg)
        print(f'fill {ff}: n {len(tr)} win {(tr.r>0).mean():.3f} E {tr.r.mean():.3f} t {T(tr.r):.2f}  exits {tr.exit_reason.value_counts().to_dict()}')
st=GapFade(tz='America/New_York',min_gap_atr=0.2,fill_fraction=1.0)
cfg=BacktestConfig(risk=RiskConfig(cost_per_trade=0.5,exit_time='15:55',target_mode='strategy'))
rep=validate(rth5,st,cfg,n_trials=100,n_random=300)
s=rep['summary']
print('\nVALIDACE gap fill (100 pokusů pro DSR):', {k:round(s[k],3) for k in ('trades','win_rate','expectancy_r','t_stat','profit_factor','max_drawdown_r','sharpe_annual')})
print('bootstrap',{k:round(v,3) for k,v in rep['bootstrap'].items()}); print('random',{k:round(v,3) for k,v in rep['random_direction'].items()})
print('DSR',{k:round(v,3) for k,v in rep['deflated_sharpe'].items()}); print('MC 1%',{k:round(v,3) for k,v in rep['monte_carlo'].items()})
print(rep['by_year'].round(3).to_string()); print(rep['verdict'])
rep['trades'].to_csv('out/gapfill_trades.csv',index=False)
