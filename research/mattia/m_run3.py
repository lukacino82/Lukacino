import sys, pickle, time
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import numpy as np, pandas as pd
from families import *
B=pickle.load(open('/tmp/claude-0/data/m_bars.pkl','rb'))
G=pickle.load(open('/tmp/claude-0/data/m_grid.pkl','rb'))
def ev(name, r, expo=None):
    r=r.dropna(); b=bh(G).reindex(r.index)
    out={'name':name}
    for lab,a,z in [('ALL','2008','2027'),('PRE','2008','2017-12-31'),('IS','2018','2022-12-31'),('OOS','2023','2027')]:
        x=r[a:z]; bb=b[a:z]
        if len(x)<50: continue
        sh=x.mean()/x.std()*np.sqrt(252) if x.std()>0 else np.nan
        X=np.c_[np.ones(len(bb)),bb.values]; beta=np.linalg.lstsq(X,x.values,rcond=None)[0]
        res=x.values-X@beta; se=np.sqrt(res.var(ddof=2)/len(x))/1
        out[lab+'_ann%']=round(x.mean()*252*100,2); out[lab+'_SR']=round(sh,2)
        if lab=='ALL':
            out['beta']=round(beta[1],2); out['alpha_ann%']=round(beta[0]*252*100,2); out['alpha_t']=round(beta[0]/se,2)
            eq=(1+x).cumprod(); out['maxDD%']=round((eq/eq.cummax()-1).min()*100,1); out['expo%']=round((x!=0).mean()*100,1)
    return out
rows=[ev('Buy&hold ES',bh(G))]
rows.append(ev('Overnight 16:00->09:30',overnight(G)))
rows.append(ev('Overnight GROSS',overnight(G,0)))
rows.append(ev('RTH GROSS',rth_only(G,0)))
rows.append(ev('Hour bias WF GROSS',hour_bias_wf(G,cost=0)[0]))
rows.append(ev('Noise L/S GROSS',noise_momentum(G,cost=0)[0]))
rows.append(ev('RTH 09:30->16:00',rth_only(G)))
hb,picks=hour_bias_wf(G); rows.append(ev('Hour bias WF (5y, top6/bot2)',hb))
for lb,tp,bt in [(3,4,1),(5,4,0),(8,6,2),(5,8,0)]:
    rows.append(ev(f'Hour bias WF ({lb}y, top{tp}/bot{bt})',hour_bias_wf(G,lb,tp,bt)[0]))
rows.append(ev('Intraday momentum Gao',intraday_momentum(G)))
nm,nt=noise_momentum(G); rows.append(ev(f'Noise-area momentum L/S ({nt} tr)',nm))
nl,nt2=noise_momentum(G,both=False); rows.append(ev(f'Noise-area momentum long ({nt2} tr)',nl))
rows.append(ev('Turn of month',turn_of_month(G)))
rows.append(ev('Pre-holiday',pre_holiday(G)))
rows.append(ev('Pre-FOMC 24h (2016+)',pre_fomc(G)))
rows.append(ev('OPEX week',opex_week(G)))
rows.append(ev('IBS<0.2 & bull, 1 day',ibs_bull(G)))
for k,(w,s) in exposure_overlays(G).items():
    rows.append(ev(k,w*s))
pd.set_option('display.width',260); pd.set_option('display.max_columns',30)
print(pd.DataFrame(rows).to_string())

ht=hour_table(G); print((ht.mean()*1e4).round(2).to_dict())
