import sys, pickle
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import numpy as np, pandas as pd
res=pickle.load(open('/tmp/claude-0/data/m_res1.pkl','rb'))
G=pickle.load(open('/tmp/claude-0/data/m_grid.pkl','rb'))
days=G.days
def daily_usd(keys, mes=2, cost=0.5):
    s=pd.Series(0.0,index=days)
    for k in keys:
        t=res[k]; s=s.add(((t.pnl-cost)*5*mes).groupby(t.date).sum(),fill_value=0)
    return s.reindex(days).fillna(0)
def challenge(pnl, target=3000, trail=2000, maxdays=60):
    v=pnl.values; n=len(v); out=[]
    for st in range(0,n-maxdays):
        eq=0; peak=0; res_='timeout'
        for k in range(st,st+maxdays):
            eq+=v[k]; peak=max(peak,eq)
            if eq>=target: res_='pass'; break
            if eq<=peak-trail: res_='fail'; break
        out.append((days[st],res_,k-st+1))
    return pd.DataFrame(out,columns=['start','res','days'])
rows=[]
for name,keys in [('S1',['S1']),('S2',['S2']),('S3',['S3']),('S1+S2+S3',['S1','S2','S3'])]:
    for mes in [2,5]:
        c=challenge(daily_usd(keys,mes))
        c['per']=np.where(c.start<'2018',"PRE 08-17",np.where(c.start<'2023',"IS 18-22","OOS 23-26"))
        d={'book':name,'MES/strategie':mes}
        for p,g in c.groupby('per'): d[p]=f"{(g.res=='pass').mean()*100:.0f}% (fail {(g.res=='fail').mean()*100:.0f}%)"
        d['median dní k pass']=int(c[c.res=='pass'].days.median()) if (c.res=='pass').any() else None
        rows.append(d)
# baseline: coin-flip-like - random long intraday RTH with same daily risk? use B&H intraday 2 MES
rth=pd.Series((G.C-G.O-0.5)*10,index=days).fillna(0)
c=challenge(rth); c['per']=np.where(c.start<'2018',"PRE 08-17",np.where(c.start<'2023',"IS 18-22","OOS 23-26"))
d={'book':'Placebo: long RTH open->close každý den','MES/strategie':2}
for p,g in c.groupby('per'): d[p]=f"{(g.res=='pass').mean()*100:.0f}% (fail {(g.res=='fail').mean()*100:.0f}%)"
rows.append(d)
pd.set_option('display.width',250); print(pd.DataFrame(rows).to_string())
