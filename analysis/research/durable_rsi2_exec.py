"""RSI(2) – realistická exekuce (vstup/výstup na open dalšího dne), nejhorší obchody,
katastrofický stop a časový stop."""
import os
import numpy as np, pandas as pd
S=os.environ.get('SCRATCH','out'); COST=0.5
d=pd.read_pickle(f'{S}/es_daily_adj.pkl')
x=d.c.diff(); up=x.clip(lower=0).ewm(alpha=.5,adjust=False).mean(); dn=(-x.clip(upper=0)).ewm(alpha=.5,adjust=False).mean()
d['rsi']=100-100/(1+up/dn); d['ma5']=d.c.rolling(5).mean(); d['ma200']=d.c.rolling(200).mean()
d['atr']=(d.c.diff().abs()).rolling(20).mean()   # hrubý denní range close-close
d=d.dropna()
o,c,r,ma5,m200,atr=(d[k].values for k in ('o','c','rsi','ma5','ma200','atr'))
def run(next_open=False, stop_atr=None, max_days=None, trend=True, th=10):
    out=[]; pos=False
    for i in range(1,len(c)-1):
        if pos:
            held=i-ei
            # katastrofický stop na close (denní data – konzervativně na close)
            if stop_atr and c[i]<=ent-stop_atr*a0:
                px=o[i+1] if next_open else c[i]; out.append((d.index[ei],px-ent-COST,held,mae)); pos=False; continue
            mae=min(mae,c[i]-ent)
            if c[i]>ma5[i] or (max_days and held>=max_days):
                px=o[i+1] if next_open else c[i]; out.append((d.index[ei],px-ent-COST,held,mae)); pos=False
        elif r[i]<th and (not trend or c[i]>m200[i]):
            pos=True; ei=i; ent=o[i+1] if next_open else c[i]; a0=atr[i]; mae=0.0
    return pd.DataFrame(out,columns=['date','pts','days','mae'])
def show(name,t):
    p=t.pts; eq=p.cumsum(); dd=(eq-eq.cummax()).min()
    print(f'{name:45s} n {len(p):3d}  {p.mean():6.1f} b./obchod  t {p.mean()/p.std()*np.sqrt(len(p)):.2f}  win {(p>0).mean():.2f}  nejhorší {p.min():7.1f}  maxDD {dd:7.1f}  celkem {p.sum():7.0f}')
show('základ (vstup/výstup na close)',run())
show('vstup/výstup na OPEN dalšího dne',run(next_open=True))
show('+ katastrofický stop 3×ATR',run(stop_atr=3))
show('+ katastrofický stop 2×ATR',run(stop_atr=2))
show('+ časový stop 7 dní',run(max_days=7))
show('bez MA200, open dalšího dne',run(next_open=True,trend=False))
t=run(); print('\nnejhorší obchody (základ):'); print(t.sort_values('pts').head(5).round(1).to_string(index=False))
print('MAE (nejhorší průběžná ztráta) kvantily:',t.mae.quantile([.5,.9,.99]).round(1).to_dict(), 'min',t.mae.min().round(1))
t['y']=t.date.dt.year; print(t.groupby('y').pts.agg(['count','sum']).round(0).to_dict('index'))
