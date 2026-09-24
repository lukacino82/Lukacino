"""Datová vrstva pro order-flow / VWAP / market profile hypotézy na ES.

Z 1min Sierra Chart exportu (Bid/AskVolume) spočítá:
* back-adjustované ceny (33 rolů), deltu = AskVol - BidVol, CVD za RTH
* RTH VWAP + σ pásma (objemově vážené), týdenní VWAP
* denní RTH volume profile: POC, VAH, VAL (70 %), IB (09:30–10:30), overnight high/low
Uloží bars5 (5min RTH bary s featurami) a daily (denní úrovně) do SCRATCH.
"""
import os
import numpy as np, pandas as pd
S=os.environ.get('SCRATCH','out'); TICK=0.25
raw=pd.read_csv(os.environ.get('ES_TXT',f'{S}/data/ES3000.txt'),skipinitialspace=True)
raw.columns=[c.strip().lower() for c in raw.columns]
ts=pd.to_datetime(raw['date'].str.strip()+' '+raw['time'].str.strip(),format='%Y/%m/%d %H:%M:%S')
df=pd.DataFrame({'open':raw.open,'high':raw.high,'low':raw.low,'close':raw['last'],'vol':raw.volume,
                 'bid':raw.bidvolume,'ask':raw.askvolume}).astype(float)
df.index=pd.DatetimeIndex(ts).tz_localize('America/New_York',ambiguous='NaT',nonexistent='shift_forward')
df=df[df.index.notna()]; df=df[~df.index.duplicated()].sort_index()
# roll adjust (neděle po 2. čtvrtku v rolovacím měsíci)
m=(df.index.hour==18)&(df.index.minute==0)&(df.index.dayofweek==6)&df.index.month.isin([3,6,9,12])
adj=np.zeros(len(df))
for ts_ in df.index[m]:
    thu=[d for d in pd.date_range(ts_.replace(day=1).date(),periods=14) if d.dayofweek==3][1]
    if ts_.date()==(thu+pd.Timedelta(days=3)).date():
        i=df.index.get_loc(ts_); adj[:i]+=df.open.iloc[i]-df.close.iloc[i-1]
for k in ('open','high','low','close'): df[k]+=adj
df['delta']=df.ask-df.bid
tm=df.index.time
df['rth']=(tm>=pd.Timestamp('09:30').time())&(tm<pd.Timestamp('16:00').time())
# obchodní den: seance 18:00 -> 17:00 další den patří dni následujícímu
sd=(df.index+pd.Timedelta(hours=6)).normalize().tz_localize(None)
df['sday']=sd
rth=df[df.rth].copy()
g=rth.groupby('sday')
tp=(rth.high+rth.low+rth.close)/3
rth['cum_v']=g.vol.cumsum(); rth['cum_pv']=(tp*rth.vol).groupby(rth.sday).cumsum(); rth['cum_p2v']=(tp*tp*rth.vol).groupby(rth.sday).cumsum()
rth['vwap']=rth.cum_pv/rth.cum_v
rth['vwap_sd']=np.sqrt((rth.cum_p2v/rth.cum_v-rth.vwap**2).clip(lower=0))
rth['cvd']=g.delta.cumsum()
# --- denní profil
def profile(day):
    lo=np.floor(day.low.min()/TICK); hi=np.ceil(day.high.max()/TICK); n=int(hi-lo)+1
    vp=np.zeros(n)
    for l,h,v in zip(day.low.values,day.high.values,day.vol.values):
        a=int(np.floor(l/TICK)-lo); b=int(np.ceil(h/TICK)-lo); vp[a:b+1]+=v/(b-a+1)
    poc=int(vp.argmax()); tot=vp.sum(); inc=vp[poc]; a=b=poc
    while inc<0.7*tot:
        up=vp[b+1] if b+1<n else -1; dn=vp[a-1] if a>0 else -1
        if up>=dn: b+=1; inc+=up
        else: a-=1; inc+=dn
    return (lo+poc)*TICK,(lo+b)*TICK,(lo+a)*TICK
rows=[]
full=df.groupby('sday')
for d,day in g:
    if len(day)<300: continue
    poc,vah,val=profile(day)
    ib=day[day.index.time<pd.Timestamp('10:30').time()]
    on=full.get_group(d); on=on[~on.rth & (on.index.time<pd.Timestamp('09:30').time()) | (~on.rth & (on.index.hour>=18))]
    rows.append(dict(sday=d,o=day.open.iloc[0],h=day.high.max(),l=day.low.min(),c=day.close.iloc[-1],vol=day.vol.sum(),
        delta=day.delta.sum(),poc=poc,vah=vah,val=val,ibh=ib.high.max(),ibl=ib.low.min(),
        onh=on.high.max() if len(on) else np.nan,onl=on.low.min() if len(on) else np.nan,
        on_delta=on.delta.sum() if len(on) else np.nan,vwap_close=day.vwap.iloc[-1]))
daily=pd.DataFrame(rows).set_index('sday')
# 5min RTH bary
agg=dict(open='first',high='max',low='min',close='last',vol='sum',delta='sum',vwap='last',vwap_sd='last',cvd='last',sday='first')
b5=rth.resample('5min',label='left',closed='left').agg(agg).dropna(subset=['close'])
b5=b5[b5.sday.isin(daily.index)]
b5.to_pickle(f'{S}/of_bars5.pkl'); daily.to_pickle(f'{S}/of_daily.pkl')
print('dní',len(daily),'5min barů',len(b5)); print(daily.tail(3).round(2).to_string())
print('delta sanity: corr(denní delta, denní změna)=%.3f'%np.corrcoef(daily.delta,daily.c-daily.o)[0,1])
