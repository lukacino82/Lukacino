"""Primitivní systémy s parametry pevně z literatury (publikované před 2018),
testované na ES 2018–2026 jako čistý out-of-sample. Žádná optimalizace."""
import os
import numpy as np, pandas as pd
S=os.environ.get('SCRATCH','out'); OUT=os.environ.get('OUT','reports/es_durable')
os.makedirs(OUT,exist_ok=True)
df=pd.read_pickle(os.environ.get('ES_PKL',f'{S}/data/es1m.pkl'))
COST=0.5  # body na round-trip
# --- back-adjust: roll v neděli po 2. čtvrtku v březnu/červnu/září/prosinci
px=df[['open','high','low','close']].copy()
m=(px.index.hour==18)&(px.index.minute==0)&(px.index.dayofweek==6)
cands=px.index[m]
rolls=[]
for ts in cands:
    if ts.month not in (3,6,9,12): continue
    thursdays=[d for d in pd.date_range(ts.replace(day=1).date(),periods=14) if d.dayofweek==3]
    second_thu=thursdays[1]
    if ts.date()==(second_thu+pd.Timedelta(days=3)).date(): rolls.append(ts)
adj=pd.Series(0.0,index=px.index)
for ts in rolls:
    i=px.index.get_loc(ts); gap=px.open.iloc[i]-px.close.iloc[i-1]
    adj.iloc[:i]+=gap
px=px.add(adj,axis=0)
print('rolů:',len(rolls),' celková úprava',round(adj.iloc[0],1),'bodů')
t=px.index.time
rth=px[(t>=pd.Timestamp('09:30').time())&(t<pd.Timestamp('16:00').time())]
g=rth.groupby(rth.index.date)
d=pd.DataFrame({'o':g.open.first(),'c':g.close.last(),'n':g.size()}); d.index=pd.to_datetime(d.index)
d=d[d.n>=200].drop(columns='n')   # vynechat zkrácené/prázdné dny
d['ma200']=d.c.rolling(200).mean(); d['ma5']=d.c.rolling(5).mean()
diff=d.c.diff(); up=diff.clip(lower=0).ewm(alpha=1/2,adjust=False).mean(); dn=(-diff.clip(upper=0)).ewm(alpha=1/2,adjust=False).mean()
d['rsi2']=100-100/(1+up/dn)
d=d[d.index>=d.index[200]]  # po zahřátí MA200 (od ~05/2019)
def stats(name,pnl,trades,exposure):
    pnl=pnl.fillna(0); eq=pnl.cumsum(); dd=(eq-eq.cummax()).min()
    daily_t=pnl.mean()/pnl.std()*np.sqrt(len(pnl))
    yrs=pnl.groupby(pnl.index.year).sum()
    return dict(system=name,trades=trades,exposure=exposure,total_pts=eq.iloc[-1],pts_per_trade=eq.iloc[-1]/max(trades,1),
                t=daily_t,max_dd=dd,ret_dd=eq.iloc[-1]/-dd if dd<0 else np.inf,pos_years=f'{(yrs>0).sum()}/{len(yrs)}',
                **{str(y):round(v,0) for y,v in yrs.items()})
res=[]
cc=d.c.diff()
res.append(stats('Buy & hold (close-close)',cc,1,1.0))
on=(d.o-d.c.shift(1))-COST; res.append(stats('1) Noční držení: RTH close -> open',on,len(on)-1,0.73))
intr=(d.c-d.o)-COST; res.append(stats('   pro srovnání: den open -> close',intr,len(intr),0.27))
on_tr=np.where(d.c.shift(1)>d.ma200.shift(1),on,0.0); on_tr=pd.Series(on_tr,index=d.index)
res.append(stats('1b) Noční držení jen nad MA200',on_tr,int((on_tr!=0).sum()),None))
# 2) RSI2 Connors
pos=0; pnl=[]; n=0; days_in=0
for i in range(1,len(d)):
    r=0.0
    if pos: r=d.c.iloc[i]-d.c.iloc[i-1]; days_in+=1
    if pos and d.c.iloc[i]>d.ma5.iloc[i]: pos=0; r-=COST
    elif not pos and d.rsi2.iloc[i]<10 and d.c.iloc[i]>d.ma200.iloc[i]: pos=1; n+=1
    pnl.append(r)
res.append(stats('2) RSI(2)<10 nad MA200, exit > MA5',pd.Series(pnl,index=d.index[1:]),n,days_in/len(d)))
# 3) Turn of month: drž od close předposledního dne do close 3. dne
ym=d.index.to_period('M'); rk=d.groupby(ym).cumcount(); rrk=d.groupby(ym).cumcount(ascending=False)
inpos=((rrk==0)|(rk<=2)).astype(float).values  # den, jehož close-close výnos držíme
tom=pd.Series(cc.values*inpos,index=d.index); ntr=int(((rrk==0)).sum())
tom=tom-np.where(rk==2,COST,0.0)
res.append(stats('3) Turn-of-month (den -1 až +3)',tom,ntr,inpos.mean()))
# 4) Trend MA200
st=(d.c>d.ma200).astype(int).shift(1).fillna(0); tr=cc*st-st.diff().abs().fillna(0)*COST/2
res.append(stats('4) Trend: long nad MA200',tr,int(st.diff().abs().sum()/2),st.mean()))
R=pd.DataFrame(res).set_index('system')
pd.set_option('display.width',250)
print(R.round(2).to_string())
R.to_csv(f'{OUT}/durable_systems.csv')
d[['o','c']].to_pickle(f'{S}/es_daily_adj.pkl')
