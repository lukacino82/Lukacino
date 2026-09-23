import os
import pandas as pd, numpy as np
df=pd.read_pickle(os.environ.get('ES_PKL', 'data/es1m.pkl'))
t=df.index.time
rth=df[(t>=pd.Timestamp('09:30').time())&(t<pd.Timestamp('16:00').time())]
def tstat(x): x=pd.Series(x).dropna(); return x.mean()/x.std()*np.sqrt(len(x))
# variance ratio within RTH: 5min base
r5=np.log(rth.close).groupby(rth.index.date).apply(lambda s: s.resample('5min').last().diff().dropna())
r5=r5.droplevel(0) if isinstance(r5.index,pd.MultiIndex) else r5
print('== Variance ratio (RTH, základ 5 min; <1 = návrat k průměru, >1 = momentum)')
for k in (2,3,6,12,24):
    g=r5.groupby([r5.index.date, np.arange(len(r5))//k])
    agg=g.sum()[g.size()==k]
    vr=agg.var()/(k*r5.var()); print(f'  {5*k:>3} min: VR={vr:.3f}')
# by year VR 30min
for y in sorted(set(r5.index.year)):
    x=r5[r5.index.year==y]; g=x.groupby([x.index.date,np.arange(len(x))//6]); agg=g.sum()[g.size()==6]
    print('   ',y,'VR30=%.3f'%(agg.var()/(6*x.var())))
# daily
g=rth.groupby(rth.index.date); d=pd.DataFrame({'o':g.open.first(),'c':g.close.last()}); d.index=pd.to_datetime(d.index)
full=df.groupby(df.index.date).close.last()
d['cc']=np.log(d.c/d.c.shift(1)); d['on']=np.log(d.o/d.c.shift(1)); d['day']=np.log(d.c/d.o)
d['next_on']=d.on.shift(-1); d['next_day']=d.day.shift(-1); d['next_cc']=d.cc.shift(-1)
print('\n== Po velkém dni (close-close kvintily) -> další den (bp)')
q=pd.qcut(d.cc,5); print((d.groupby(q,observed=True)[['next_on','next_day','next_cc']].mean()*1e4).round(2))
x=d.dropna(subset=['cc','next_cc']); bot=x.cc<x.cc.quantile(0.2)
print('  po dolním kvintilu: next_cc t=%.2f, next_on t=%.2f, next_day t=%.2f n=%d'%(tstat(x.next_cc[bot]),tstat(x.next_on[bot]),tstat(x.next_day[bot]),bot.sum()))
# turn of month
d['ym']=d.index.to_period('M'); d['rank']=d.groupby('ym').cumcount(); d['rrank']=d.groupby('ym').cumcount(ascending=False)
tom=(d['rrank']==0)|(d['rank']<=2)
print('\n== Turn-of-month (poslední + první 3 dny): cc bp %.2f t %.2f | ostatní %.2f t %.2f'%(d.cc[tom].mean()*1e4,tstat(d.cc[tom]),d.cc[~tom].mean()*1e4,tstat(d.cc[~tom])))
print('   TOM po letech:',(d.cc[tom].groupby(d.index[tom].year).mean()*1e4).round(1).to_dict())
print('\n== Den v týdnu (cc bp, t):'); 
for k,v in d.cc.groupby(d.index.dayofweek): print('  ',k,round(v.mean()*1e4,2),round(tstat(v),2))
