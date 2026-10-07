import sys, pickle
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import numpy as np, pandas as pd
from families import *
G=pickle.load(open('/tmp/claude-0/data/m_grid.pkl','rb'))
def ev(r):
    out={}
    for lab,a,z in [('ALL','2008','2027'),('PRE','2008','2017-12-31'),('IS','2018','2022-12-31'),('OOS','2023','2027')]:
        x=r[a:z]; out[lab]=round(x.mean()/x.std()*np.sqrt(252),2)
    out['ann%']=round(r.mean()*252*100,2); eq=(1+r).cumprod(); out['DD%']=round((eq/eq.cummax()-1).min()*100,1)
    return out
rows=[]
for vm in [1.0,1.25,1.5,2.0]:
  for lb in [14,30]:
    for sq in [1,2]:
      for both in [True,False]:
        for cost in [0,0.25,0.5,1.0]:
          r,nt=noise_momentum(G,lookback=lb,start_q=sq,both=both,vm=vm,cost=cost)
          rows.append(dict(vm=vm,lb=lb,start=('10:00' if sq==1 else '10:30'),side='L/S' if both else 'L',cost=cost,trades=nt,**ev(r)))
df=pd.DataFrame(rows); pd.set_option('display.width',250); pd.set_option('display.max_rows',300)
print(df[df.cost==0.5].sort_values('ALL',ascending=False).to_string())
print(df.pivot_table(index=['vm','side'],columns='cost',values='ALL',aggfunc='mean').round(2))
df.to_csv('/tmp/claude-0/data/noise_grid.csv',index=False)
