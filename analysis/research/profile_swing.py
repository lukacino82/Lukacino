"""Robustnost swing hypotézy S3: 'close pod VAL dne -> long' (čistý market profile).
Varianty držení, výstup podle profilu, potvrzení deltou, nulová hypotéza."""
import os
import numpy as np, pandas as pd
S=os.environ.get('SCRATCH','out'); COST=0.5
D=pd.read_pickle(f'{S}/of_daily.pkl'); c=D.c.values
def T(p): p=np.asarray(p); return p.mean()/p.std(ddof=1)*np.sqrt(len(p))
def yrs(p,idx): s=pd.Series(p,index=idx); y=s.groupby(s.index.year).mean(); return f'{(y>0).sum()}/{len(y)}'
sig=(D.c<D.val).values
print('== pevné držení N dní (vstup close signálního dne, výstup close +N)')
for N in (1,2,3,5,10):
    idx=np.flatnonzero(sig[:-N]); p=c[idx+N]-c[idx]-COST
    bh=np.array([c[i+N]-c[i] for i in range(len(c)-N)]).mean()
    print(f'  N={N:2d}: n {len(p)}  {p.mean():6.2f} b.  t {T(p):.2f}  kladné roky {yrs(p,D.index[idx])}   | buy&hold stejné N: {bh:5.2f} b.')
print('== výstup podle profilu: drž, dokud close není nad POC dne vstupu (max 10 dní)')
out=[];dts=[];held=[]
i=0
while i<len(c)-1:
    if sig[i]:
        poc=D.poc.values[i]; e=c[i]
        for j in range(i+1,min(i+11,len(c))):
            if c[j]>poc or j==min(i+10,len(c)-1): break
        out.append(c[j]-e-COST); dts.append(D.index[i]); held.append(j-i); i=j; continue
    i+=1
out=np.array(out); print(f'  n {len(out)}  {out.mean():.2f} b.  t {T(out):.2f}  win {(out>0).mean():.2f}  prům. držení {np.mean(held):.1f} d  kladné roky {yrs(out,pd.DatetimeIndex(dts))}  nejhorší {out.min():.1f}')
eq=np.cumsum(out); print(f'  celkem {eq[-1]:.0f} b.  max DD {(eq-np.maximum.accumulate(eq)).min():.0f} b.')
print('== potvrzení deltou (absorpce): close pod VAL a denní delta >0 vs <0, drž 1 den')
for name,m in (('delta > 0 (kupci absorbují)',sig&(D.delta.values>0)),('delta < 0',sig&(D.delta.values<0))):
    idx=np.flatnonzero(m[:-1]); p=c[idx+1]-c[idx]-COST; print(f'  {name:28s} n {len(p)}  {p.mean():6.2f} b.  t {T(p):.2f}')
print('== hloubka pod VAL (v % VA šířky), drž 1 den')
depth=((D.val-D.c)/(D.vah-D.val)).values
for lo,hi in ((0,0.25),(0.25,0.75),(0.75,99)):
    m=sig&(depth>lo)&(depth<=hi); idx=np.flatnonzero(m[:-1]); p=c[idx+1]-c[idx]-COST; print(f'  {lo}-{hi}: n {len(p)}  {p.mean():6.2f} b.  t {T(p):.2f}')
print('== nulová hypotéza: náhodné dny, držení 1 den (20 000 vzorků)')
idx=np.flatnonzero(sig[:-1]); real=(c[idx+1]-c[idx]-COST).mean(); rng=np.random.default_rng(0)
allr=c[1:]-c[:-1]-COST; null=np.array([rng.choice(allr,len(idx)).mean() for _ in range(20000)])
print(f'  skutečnost {real:.2f} b. | náhodné dny průměr {null.mean():.2f}, 95% {np.quantile(null,.95):.2f}, p={(null>=real).mean():.4f}')
print('== symetrie: close nad VAH -> short 1 den (pokud je to čistá reverze, mělo by fungovat i naopak)')
m=(D.c>D.vah).values; idx=np.flatnonzero(m[:-1]); p=c[idx]-c[idx+1]-COST; print(f'  n {len(p)}  {p.mean():.2f} b.  t {T(p):.2f}')
