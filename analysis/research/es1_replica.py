"""Rekonstrukce ES1: long, když 1min close > high 09:30–09:45; vstup na open dalšího
baru (do 11:30), SL 10 b., TP 30 b., výstup 15:56, max 1 obchod denně."""
import os
import numpy as np, pandas as pd
S=os.environ.get('SCRATCH','out')
df=pd.read_pickle(os.environ.get('ES_PKL',f'{S}/data/es1m.pkl'))
t=df.index.time
rth=df[(t>=pd.Timestamp('09:30').time())&(t<pd.Timestamp('16:00').time())]
T=lambda s:pd.Timestamp(s).time()
def run(sl=10.0, tp=30.0, last_entry='11:30', exit_t='15:56', rng_end='09:45', trail=None):
    rows=[]
    for d,g in rth.groupby(rth.index.date):
        tm=g.index.time; o,h,l,c=(g[k].values for k in ('open','high','low','close'))
        r=tm<T(rng_end)
        if r.sum()<5: continue
        orh=h[r].max()
        cand=np.flatnonzero((~r)&(tm<=T(last_entry))&(c>orh))
        if not len(cand) or cand[0]+1>=len(g): continue
        s=cand[0]+1
        if tm[s]>T(last_entry): continue
        e=o[s]; stop=e-sl; tgt=e+tp; ex=None
        endi=np.flatnonzero(tm>=T(exit_t)); endi=endi[0] if len(endi) else len(g)-1
        for j in range(s,endi):
            if l[j]<=stop: ex=(stop,'stop',j); break
            if h[j]>=tgt: ex=(tgt,'target',j); break
        if ex is None: ex=(o[endi],'time',endi)
        rows.append(dict(date=pd.Timestamp(d),entry_time=g.index[s],entry=e,exit=ex[0],reason=ex[1],pts=ex[0]-e))
    return pd.DataFrame(rows)
if __name__=='__main__':
    rp=run(); rp.to_pickle(f'{S}/es1_replica.pkl')
    tr=pd.read_pickle(f'{S}/es1_trades.pkl')
    m=(rp.date>=tr.entry.min().normalize())&(rp.date<=tr.exit.max().normalize()); p=rp[m]
    real_days=set(tr.entry.dt.normalize())
    both=p[p.date.isin(real_days)]
    print('období ES1: replika',len(p),'obchodů, skutečnost',len(tr),'| shodné dny',len(both))
    j=both.merge(tr.assign(date=tr.entry.dt.normalize())[['date','pts','Entry Price']],on='date',suffixes=('_rep','_real'))
    print('shoda vstupní ceny ±0.5b: %.2f, shoda výsledku (znaménko): %.2f'%((abs(j.entry-j['Entry Price'])<=0.5).mean(),(np.sign(j.pts_rep)==np.sign(j.pts_real)).mean()))
    print('replika v období: %.2f b./obchod, skutečnost %.2f'%(p.pts.mean(),tr.pts.mean()))
    rp['y']=rp.date.dt.year
    print(rp.groupby('y').pts.agg(['count','mean','sum']).round(2).to_string())
    x=rp.pts; print('CELKEM 2018-2026: n %d, %.2f b./obchod, t %.2f, win %.2f'%(len(x),x.mean(),x.mean()/x.std()*np.sqrt(len(x)),(x>0).mean()))
