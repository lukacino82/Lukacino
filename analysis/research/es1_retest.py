"""Hypotéza: po potvrzení průrazu (close > high 09:30–09:45) vstoupit limitkou
na retestu high rangu (ORH - offset), ne marketem. Stejné SL/TP/výstup jako ES1."""
import os
import numpy as np, pandas as pd
S=os.environ.get('SCRATCH','out')
df=pd.read_pickle(os.environ.get('ES_PKL',f'{S}/data/es1m.pkl'))
t=df.index.time; rth=df[(t>=pd.Timestamp('09:30').time())&(t<pd.Timestamp('16:00').time())]
T=lambda s:pd.Timestamp(s).time()
def run(offset=0.0, sl=10.0, tp=30.0, last_entry='11:30', exit_t='15:56'):
    rows=[]
    for d,g in rth.groupby(rth.index.date):
        tm=g.index.time; o,h,l,c=(g[k].values for k in ('open','high','low','close'))
        r=tm<T('09:45')
        if r.sum()<5: continue
        orh=h[r].max(); cand=np.flatnonzero((~r)&(tm<=T(last_entry))&(c>orh))
        if not len(cand): continue
        lim=orh-offset; s=None
        for j in range(cand[0]+1,len(g)):
            if tm[j]>T(last_entry): break
            if l[j]<=lim: s=j; break
        if s is None: continue
        e=min(lim,o[s]); stop=e-sl; tgt=e+tp; ex=None
        endi=np.flatnonzero(tm>=T(exit_t)); endi=endi[0] if len(endi) else len(g)-1
        for j in range(s,endi):
            if l[j]<=stop: ex=(stop,j); break
            if h[j]>=tgt and j>s: ex=(tgt,j); break   # na vstupním baru TP nepočítáme (konzervativně)
        if ex is None: ex=(o[endi],endi)
        rows.append(dict(date=pd.Timestamp(d),pts=ex[0]-e))
    return pd.DataFrame(rows)
for off in (0.0,2.0,4.0):
    x=run(off); p=x.pts; y=x.groupby(x.date.dt.year).pts.mean().round(2).to_dict()
    net=p-0.5
    print(f'retest ORH-{off}: n {len(p)} hrubě {p.mean():.2f} b. (t {p.mean()/p.std()*np.sqrt(len(p)):.2f}) | po nákl. {net.mean():.2f} (t {net.mean()/net.std()*np.sqrt(len(p)):.2f}) | roky {y}')
