"""Equity křivky a analýza sérií ztrát pro ES1 (skutečné obchody + 8letá rekonstrukce)."""
import os, json
import numpy as np, pandas as pd
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
S=os.environ.get('SCRATCH','out'); OUT=os.environ.get('OUT','reports/es1')
PV=50.0; COST=0.5  # $ za bod ES, náklady v bodech na round-trip (~$25)
real=pd.read_pickle(f'{S}/es1_trades.pkl').sort_values('entry'); rep=pd.read_pickle(f'{S}/es1_replica.pkl')
BLUE,ORANGE,INK,MUTED,GRID,SURF='#2a78d6','#eb6834','#0b0b0b','#52514e','#e4e3df','#fcfcfb'
plt.rcParams.update({'font.size':10,'axes.edgecolor':GRID,'axes.labelcolor':MUTED,'xtick.color':MUTED,'ytick.color':MUTED,
                     'axes.spines.top':False,'axes.spines.right':False,'figure.facecolor':SURF,'axes.facecolor':SURF})
def streak_stats(x):
    ls=[]; ws=[]; c=0; w=0
    for v in x:
        if v<0: c+=1; (ws.append(w) if w else None); w=0
        else: w+=1; (ls.append(c) if c else None); c=0
    if c: ls.append(c)
    if w: ws.append(w)
    return np.array(ls), np.array(ws)
def dd_info(eq, dates):
    peak=np.maximum.accumulate(np.r_[0,eq])[1:]; dd=eq-peak
    # nejdelší období pod vrcholem (obchody i kalendářní dny)
    best=(0,None,None); start=None
    for i,v in enumerate(dd):
        if v<0 and start is None: start=i
        if v>=0 and start is not None:
            if i-start>best[0]: best=(i-start,dates[start],dates[i])
            start=None
    if start is not None and len(dd)-start>best[0]: best=(len(dd)-start,dates[start],None)
    return dd, best
def analyse(name, pts, dates):
    net=(pts-COST)*PV; gross=pts*PV
    ls,ws=streak_stats(net); q=(net<0).mean(); n=len(net)
    eq=np.cumsum(net); dd,longest=dd_info(eq,list(dates))
    rng=np.random.default_rng(3); sims=rng.choice(net,(5000,250))
    mx=np.array([max((len(s) for s in ''.join('L' if v<0 else 'W' for v in row).split('W')),default=0) for row in sims])
    se=np.cumsum(sims,1); sdd=(se-np.maximum.accumulate(np.concatenate([np.zeros((5000,1)),se],1),1)[:,1:]).min(1)
    r=dict(trades=n, win_rate=1-q, avg_win=net[net>0].mean(), avg_loss=net[net<0].mean(), exp_per_trade=net.mean(),
        t=net.mean()/net.std(ddof=1)*np.sqrt(n), gross_total=gross.sum(), net_total=net.sum(), max_dd=dd.min(),
        longest_dd_trades=longest[0], longest_dd_from=str(longest[1])[:10], longest_dd_to=str(longest[2])[:10],
        loss_streak_mean=ls.mean(), loss_streak_median=float(np.median(ls)), loss_streak_max=int(ls.max()),
        loss_streak_hist={int(k):int(v) for k,v in zip(*np.unique(ls,return_counts=True))},
        losses_per_win_cycle=q/(1-q), theory_mean_streak=1/(1-q),
        theory_max_streak_per_year=float(np.log(170*(1-q))/np.log(1/q)),
        mc250_max_streak_median=float(np.median(mx)), mc250_max_streak_p95=float(np.quantile(mx,.95)),
        mc250_max_dd_median=float(np.median(sdd)), mc250_max_dd_p95=float(np.quantile(sdd,.05)),
        mc250_p_negative=float((se[:,-1]<0).mean()))
    return r, net, gross, ls
rr,rnet,rgross,rls=analyse('ES1 skutečnost',real.pts.values,real.entry.values)
pr,pnet,pgross,pls=analyse('rekonstrukce',rep.pts.values,rep.date.values)
json.dump({'real':rr,'replica':pr},open(f'{OUT}/stats.json','w'),indent=1,default=float)
yr=pd.DataFrame({'pts':rep.pts.values,'net':pnet},index=rep.date.values).groupby(lambda d:d.year).agg(obchodu=('pts','size'),b_na_obchod=('pts','mean'),net_usd=('net','sum'))
yr.to_csv(f'{OUT}/by_year.csv')
# ---- graf 1: 8letá equity + drawdown
fig,(a1,a2)=plt.subplots(2,1,figsize=(11,6.4),height_ratios=[3,1.2],sharex=True)
d=rep.date.values
a1.plot(d,np.cumsum(pgross),color=BLUE,lw=2); a1.plot(d,np.cumsum(pnet),color=ORANGE,lw=2)
a1.axvspan(real.entry.min(),real.exit.max(),color='#cde2fb',alpha=.5,lw=0)
a1.text(real.entry.min(),np.cumsum(pgross).max()*0.97,' vámi testované období',color=MUTED,va='top',fontsize=9)
a1.annotate(f'hrubě ${np.cumsum(pgross)[-1]:,.0f}',(d[-1],np.cumsum(pgross)[-1]),xytext=(6,0),textcoords='offset points',color=INK,va='center',fontsize=9)
a1.annotate(f'po nákladech ${np.cumsum(pnet)[-1]:,.0f}',(d[-1],np.cumsum(pnet)[-1]),xytext=(6,0),textcoords='offset points',color=INK,va='center',fontsize=9)
a1.set_ylabel('kumulativní P/L, 1 ES ($)'); a1.grid(axis='y',color=GRID,lw=.8); a1.axhline(0,color=GRID,lw=1)
a1.set_title('ES1 (rekonstrukce) 2018–2026: long průraz 15min rangu, SL 10 b., TP 30 b., výstup 15:56',loc='left',color=INK,fontsize=11)
a1.legend(['hrubě','po nákladech (0,5 b. = $25 / obchod)'],frameon=False,loc='upper left',bbox_to_anchor=(0,0.93),fontsize=9)
eq=np.cumsum(pnet); ddv=eq-np.maximum.accumulate(np.r_[0,eq])[1:]
a2.fill_between(d,ddv,0,color=ORANGE,alpha=.35,lw=0); a2.plot(d,ddv,color=ORANGE,lw=1.2)
a2.set_ylabel('drawdown ($)'); a2.grid(axis='y',color=GRID,lw=.8)
a2.annotate(f'max −${-ddv.min():,.0f}',(d[ddv.argmin()],ddv.min()),xytext=(6,-2),textcoords='offset points',color=INK,fontsize=9)
fig.tight_layout(); fig.savefig(f'{OUT}/equity_8let.png',dpi=150); plt.close(fig)
# ---- graf 2: skutečné obchody
fig,ax=plt.subplots(figsize=(11,4.2)); de=real.entry.values
ax.plot(de,np.cumsum(rgross),color=BLUE,lw=2,marker='o',ms=3); ax.plot(de,np.cumsum(rnet),color=ORANGE,lw=2)
ax.legend(['hrubě (export Sierra Chart)','po nákladech $25 / obchod'],frameon=False,loc='upper left',fontsize=9)
ax.set_title('ES1: skutečné obchody 04/2021–02/2022 (138 obchodů, 1 ES)',loc='left',color=INK,fontsize=11)
ax.set_ylabel('kumulativní P/L ($)'); ax.grid(axis='y',color=GRID,lw=.8); ax.axhline(0,color=GRID,lw=1)
fig.tight_layout(); fig.savefig(f'{OUT}/equity_skutecne.png',dpi=150); plt.close(fig)
# ---- graf 3: rozdělení sérií ztrát (rekonstrukce) vs geometrické očekávání
fig,ax=plt.subplots(figsize=(11,3.8)); q=(pnet<0).mean(); k=np.arange(1,pls.max()+1)
obs=np.array([(pls==i).sum() for i in k]); exp=len(pls)*(1-q)*q**(k-1)
ax.bar(k-0.2,obs,width=0.38,color=BLUE,label='skutečné série (rekonstrukce 2018–2026)')
ax.bar(k+0.2,exp,width=0.38,color='#86b6ef',label=f'náhoda s P(ztráta)={q:.2f} (geometrické rozdělení)')
for i,v in zip(k,obs):
    if v: ax.text(i-0.2,v,str(v),ha='center',va='bottom',fontsize=8,color=INK)
ax.set_xticks(k); ax.set_xlabel('délka série ztrát (obchodů v řadě)'); ax.set_ylabel('počet sérií')
ax.set_title(f'Série ztrát: průměr {pls.mean():.1f}, medián {np.median(pls):.0f}, nejdelší {pls.max()}',loc='left',color=INK,fontsize=11)
ax.legend(frameon=False,fontsize=9); ax.grid(axis='y',color=GRID,lw=.8)
fig.tight_layout(); fig.savefig(f'{OUT}/serie_ztrat.png',dpi=150); plt.close(fig)
for k_,r in (('SKUTEČNOST',rr),('REKONSTRUKCE 2018-2026',pr)):
    print(k_,{kk:(round(v,2) if isinstance(v,(float,np.floating)) else v) for kk,v in r.items()})
print(yr.round(2).to_string())
