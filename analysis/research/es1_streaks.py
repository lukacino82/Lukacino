"""Analýza obchodního deníku ES1 (Sierra Chart): equity, série ztrát, Monte Carlo
a srovnání s náhodnými long vstupy se stejným SL/TP na 1min datech ES."""
import os, sys, json
import numpy as np, pandas as pd
S=os.environ.get('SCRATCH','out')
t=pd.read_pickle(f'{S}/es1_trades.pkl').sort_values('entry').reset_index(drop=True)
COST=25.0  # $ na round-trip: ~4.5 poplatky + 1 tick skluz na stopu/vstupu
t['net']=t.pnl-COST
rng=np.random.default_rng(1)
def streaks(x):
    """délky sérií ztrát (x<0) a zisků"""
    out={'loss':[], 'win':[]}; cur=None; n=0
    for v in x:
        k='loss' if v<0 else 'win'
        if k==cur: n+=1
        else:
            if cur: out[cur].append(n)
            cur, n = k, 1
    out[cur].append(n); return out
res={}
for col in ('pnl','net'):
    x=t[col].values; eq=np.cumsum(x); peak=np.maximum.accumulate(np.r_[0,eq])[1:]; dd=eq-peak
    st=streaks(x)
    # doba v drawdownu (obchody od vrcholu po nový vrchol)
    under=dd<0; runs=[]; c=0
    for u in under:
        if u: c+=1
        else:
            if c: runs.append(c); c=0
    if c: runs.append(c)
    res[col]=dict(total=float(eq[-1]), win_rate=float((x>0).mean()), avg_win=float(x[x>0].mean()), avg_loss=float(x[x<0].mean()),
        expectancy=float(x.mean()), t=float(x.mean()/x.std(ddof=1)*np.sqrt(len(x))), pf=float(x[x>0].sum()/-x[x<0].sum()),
        max_dd=float(dd.min()), longest_dd_trades=int(max(runs) if runs else 0),
        loss_streaks=st['loss'], win_streaks=st['win'])
    ls=np.array(st['loss'])
    res[col]['loss_streak_mean']=float(ls.mean()); res[col]['loss_streak_max']=int(ls.max())
    res[col]['loss_streak_hist']={int(k):int(v) for k,v in zip(*np.unique(ls,return_counts=True))}
# teoretické: P(ztráta)=q, délka série ~ geometrická
q=float((t.net<0).mean()); n=len(t)
res['theory']=dict(q=q, mean_streak=1/(1-q), exp_max_streak_138=float(np.log(n*(1-q))/np.log(1/q)),
                   exp_max_streak_250=float(np.log(250*(1-q))/np.log(1/q)), exp_max_streak_1000=float(np.log(1000*(1-q))/np.log(1/q)),
                   p_streak_ge={k:float(q**k) for k in (3,5,7,8,10,12)})
# Monte Carlo: bootstrap 250 obchodů (≈ 1 rok), max série ztrát a max DD
x=t.net.values; sims=rng.choice(x,(20000,250),replace=True)
mx=[]; 
for s in sims[:5000]:
    m=c=0
    for v in s:
        c=c+1 if v<0 else 0; m=max(m,c)
    mx.append(m)
eq=np.cumsum(sims,axis=1); dd=(eq-np.maximum.accumulate(np.concatenate([np.zeros((len(eq),1)),eq],1),axis=1)[:,1:]).min(axis=1)
res['mc_250']=dict(max_streak_median=float(np.median(mx)), max_streak_p95=float(np.quantile(mx,0.95)),
                   max_dd_median=float(np.median(dd)), max_dd_p95=float(np.quantile(dd,0.05)),
                   p_year_negative=float((eq[:,-1]<0).mean()), final_median=float(np.median(eq[:,-1])))
t[['entry','exit','pts','pnl','net']].assign(equity=t.pnl.cumsum(), equity_net=t.net.cumsum()).to_csv(f'{S}/es1_equity.csv',index=False)
json.dump(res,open(f'{S}/es1_stats.json','w'),indent=1,default=float)
for k in ('pnl','net'):
    r=res[k]; print(k,{kk:(round(v,2) if isinstance(v,float) else v) for kk,v in r.items() if kk not in ('loss_streaks','win_streaks')})
print('theory',res['theory']); print('mc',res['mc_250'])
print('loss streaks sequence:',res['net']['loss_streaks'])
