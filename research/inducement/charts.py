import pandas as pd, numpy as np, matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
plt.rcParams.update({'font.size':11,'axes.spines.top':False,'axes.spines.right':False})
A=pd.read_csv('out/A_race_total.csv')
fig,ax=plt.subplots(figsize=(8,4.5))
for i,D in enumerate([0.1,0.2,0.4]):
    r=A[A.D==D]; ax.bar(np.arange(2)+i*0.27,[r[r.set=='real'].fail_bal.iloc[0]*100,r[r.set!='real'].fail_bal.mean()*100],0.25,label=f'vzdálenost {D} ATR')
ax.axhline(50,color='k',ls='--');ax.set_xticks(np.arange(2)+0.27);ax.set_xticklabels(['skutečné úrovně','náhodné (placebo) úrovně']);ax.set_ylim(46,53)
ax.set_ylabel('Selhání průrazu (návrat) %');ax.set_title('Závod po průrazu: návrat vs pokračování (50 % = náhoda)');ax.legend();plt.tight_layout();plt.savefig('out/charts/zavod_selhani.png',dpi=130)
B=pd.read_csv('out/B_trade_cfg.csv')
g=B.groupby(['set',B.set=='real']).Rnet
fig,ax=plt.subplots(figsize=(8,4.5))
ax.hist(B[B.set=='real'].Rnet,bins=20,alpha=.7,label='skutečné úrovně');ax.hist(B[B.set!='real'].Rnet,bins=20,alpha=.7,label='placebo')
ax.axvline(0,color='k');ax.set_xlabel('Průměrné R na obchod po nákladech');ax.set_ylabel('počet konfigurací');ax.set_title('Reverzní obchod po inducementu: 0 ze 72 konfigurací je kladných');ax.legend();plt.tight_layout();plt.savefig('out/charts/rnet_hist.png',dpi=130)
S=pd.read_csv('out/C_scan_real.csv')
fig,ax=plt.subplots(figsize=(8,4.5));ax.hist(S.t,bins=25);ax.axvline(2,color='r',ls='--');ax.axvline(-2,color='r',ls='--')
ax.set_title('Rozdělení t-statistik (153 kombinací úroveň×okno×W×R): kladné t>2 = 0');ax.set_xlabel('t');plt.tight_layout();plt.savefig('out/charts/t_scan.png',dpi=130)
