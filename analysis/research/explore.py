import os
import pandas as pd, numpy as np
df=pd.read_pickle(os.environ.get('ES_PKL', 'data/es1m.pkl'))
t=df.index.time
rth=df[(t>=pd.Timestamp('09:30').time())&(t<pd.Timestamp('16:00').time())]
g=rth.groupby(rth.index.date)
d=pd.DataFrame({'o':g.open.first(),'c':g.close.last(),'h':g.high.max(),'l':g.low.min(),'n':g.size()})
d=d[d.n>=380]
d.index=pd.to_datetime(d.index)
d['on']=np.log(d.o/d.c.shift(1)); d['day']=np.log(d.c/d.o)
def tstat(x): x=x.dropna(); return x.mean()/x.std()*np.sqrt(len(x))
print('dní',len(d))
print('overnight: mean bp %.2f t %.2f | intraday: mean bp %.2f t %.2f'%(d.on.mean()*1e4,tstat(d.on),d.day.mean()*1e4,tstat(d.day)))
# 30min slots
def slot(a,b):
    m=(rth.index.time>=pd.Timestamp(a).time())&(rth.index.time<pd.Timestamp(b).time())
    x=rth[m]; gg=x.groupby(x.index.date)
    r=np.log(gg.close.last()/gg.open.first()); r.index=pd.to_datetime(r.index); return r
S={f'{h:02d}:{m:02d}':slot(f'{h:02d}:{m:02d}',(pd.Timestamp(f'{h:02d}:{m:02d}')+pd.Timedelta('30min')).strftime('%H:%M')) for h in range(9,16) for m in (0,30) if not (h==9 and m==0)}
P=pd.DataFrame(S).reindex(d.index)
print('\nprůměrný výnos 30min slotů (bp) a t-stat:')
for k in P: print(k, '%.2f'%(P[k].mean()*1e4), '%.2f'%tstat(P[k]))
first=d.on+P['09:30']
for tgt in ['15:30','15:00']:
    x=pd.concat([first,P[tgt]],axis=1).dropna()
    print(f'\ncorr(ON+first30, {tgt})=%.3f n=%d'%(x.corr().iloc[0,1],len(x)))
    s=np.sign(x.iloc[:,0])*x.iloc[:,1]
    print(' momentum strategie bp/den %.2f t %.2f'%(s.mean()*1e4,tstat(s)))
# 12th halfhour (15:00-15:30) + first -> last
x=pd.concat([first,P['15:00'],P['15:30']],axis=1).dropna(); x.columns=['f','p','l']
for name,sig in [('first',np.sign(x.f)),('15:00',np.sign(x.p)),('both agree',np.where(np.sign(x.f)==np.sign(x.p),np.sign(x.f),0))]:
    s=sig*x.l; s=s[sig!=0] if name=='both agree' else s
    print(name,'-> last30: bp %.2f t %.2f n %d'%(s.mean()*1e4,tstat(pd.Series(s)),len(s)))
# by year for first->last
s=np.sign(x.f)*x.l; print((s.groupby(s.index.year).mean()*1e4).round(2).to_dict())
# weekday of intraday return
print('\nden v týdnu intraday bp:',(d.day.groupby(d.index.dayofweek).mean()*1e4).round(2).to_dict())
print('den v týdnu overnight bp:',(d.on.groupby(d.index.dayofweek).mean()*1e4).round(2).to_dict())
# gap reversal: gap vs intraday
x=d[['on','day']].dropna(); print('\ncorr(gap, day)=%.3f'%x.corr().iloc[0,1])
q=pd.qcut(x.on,5); print((x.day.groupby(q,observed=True).mean()*1e4).round(2))
print('\n==== reverze poslední půlhodiny ====')
x=pd.concat([first,P['15:30'],d.on,P['09:30']],axis=1).dropna(); x.columns=['f','l','on','f30']
print('spearman f vs l: %.3f'%x[['f','l']].corr('spearman').iloc[0,1])
print('bez 2020: pearson %.3f'%x[x.index.year!=2020][['f','l']].corr().iloc[0,1])
print('ON vs last %.3f | first30 vs last %.3f'%(x[['on','l']].corr().iloc[0,1],x[['f30','l']].corr().iloc[0,1]))
q=pd.qcut(x.f,5); print((x.l.groupby(q,observed=True).agg(['mean','count']).assign(mean=lambda a:a['mean']*1e4)).round(2))
# celý den do 15:30 vs poslední půlhodina
upto=(d.on+P.loc[:, '09:30':'15:00'].sum(axis=1)).reindex(x.index)
y=pd.concat([upto,x.l],axis=1).dropna(); y.columns=['u','l']
print('ON+den do 15:30 vs last: pearson %.3f spearman %.3f'%(y.corr().iloc[0,1],y.corr('spearman').iloc[0,1]))
q=pd.qcut(y.u,5); print((y.l.groupby(q,observed=True).mean()*1e4).round(2))
s=-np.sign(y.u)*y.l; print('fade dne v 15:30: bp %.2f t %.2f'%(s.mean()*1e4,tstat(s)), (s.groupby(s.index.year).mean()*1e4).round(2).to_dict())
d2=P.loc[:, '09:30':'15:00'].sum(axis=1).reindex(y.index)
s=-np.sign(d2)*y.l; print('fade RTH dne (bez ON) v 15:30: bp %.2f t %.2f'%(s.mean()*1e4,tstat(s)), (s.groupby(s.index.year).mean()*1e4).round(2).to_dict())
