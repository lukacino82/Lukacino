"""Robustnost RSI(2) systému: okolí parametrů + nulová hypotéza náhodných vstupů
se stejnou délkou držení (odděluje hranu od býčího driftu)."""
import os
import numpy as np, pandas as pd
S=os.environ.get('SCRATCH','out'); COST=0.5
d=pd.read_pickle(f'{S}/es_daily_adj.pkl')
d['ma200']=d.c.rolling(200).mean()
def rsi(c,n):
    x=c.diff(); up=x.clip(lower=0).ewm(alpha=1/n,adjust=False).mean(); dn=(-x.clip(upper=0)).ewm(alpha=1/n,adjust=False).mean()
    return 100-100/(1+up/dn)
d=d.dropna()
def run(th=10, ma_exit=5, n_rsi=2, trend=True, c=None):
    c=d.c.values; r=rsi(d.c,n_rsi).values; ma=d.c.rolling(ma_exit).mean().values; m200=d.ma200.values
    pos=False; trades=[]; ent=0; ei=0
    for i in range(1,len(c)):
        if pos and c[i]>ma[i]:
            trades.append((ei,i,c[i]-ent-COST)); pos=False
        elif not pos and r[i]<th and (not trend or c[i]>m200[i]):
            pos=True; ent=c[i]; ei=i
    return trades
def T(x): x=np.array(x); return x.mean()/x.std(ddof=1)*np.sqrt(len(x))
print('== okolí parametrů (body na obchod, t, obchodů) – od 05/2019')
rows=[]
for th in (5,10,15,20,25,30):
    for me in (3,5,10):
        tr=run(th,me); p=[x[2] for x in tr]
        rows.append(dict(rsi_prah=th,exit_ma=me,n=len(p),pts=np.mean(p),t=T(p),win=np.mean(np.array(p)>0)))
R=pd.DataFrame(rows); print(R.pivot(index='rsi_prah',columns='exit_ma',values='pts').round(1).to_string())
print(R.pivot(index='rsi_prah',columns='exit_ma',values='t').round(2).to_string())
print(R.pivot(index='rsi_prah',columns='exit_ma',values='n').to_string())
tr=run(10,5,trend=False); p=[x[2] for x in tr]; print('\nbez filtru MA200: n %d, %.1f b., t %.2f'%(len(p),np.mean(p),T(p)))
tr=run(10,5,n_rsi=3); p=[x[2] for x in tr]; print('RSI(3)<10: n %d, %.1f b., t %.2f'%(len(p),np.mean(p),T(p)))
# nulová hypotéza: náhodné vstupy nad MA200 se stejnými délkami držení
base=run(10,5); real=np.mean([x[2] for x in base]); holds=[j-i for i,j,_ in base]
c=d.c.values; above=np.flatnonzero(d.c.values>d.ma200.values); rng=np.random.default_rng(0)
null=[]
for _ in range(20000):
    s=rng.choice(above[above<len(c)-40],len(holds)); null.append(np.mean([c[i+h]-c[i]-COST for i,h in zip(s,holds)]))
null=np.array(null)
print(f'\nRSI2 skutečnost {real:.1f} b./obchod | náhodný vstup nad MA200, stejné držení: průměr {null.mean():.1f}, 95% {np.quantile(null,.95):.1f}, p={(null>=real).mean():.4f}')
print('průměrná doba držení: %.1f dne'%np.mean(holds))
