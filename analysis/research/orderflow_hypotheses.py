"""Test 16 hypotéz postavených jen na tržních datech: market profile, VWAP,
cumulative delta. Jednotné měřítko: body po nákladech, t, stabilita po letech.
Víc než 30 variant -> za signál považujeme až |t| > 3."""
import os
import numpy as np, pandas as pd
S=os.environ.get('SCRATCH','out'); COST=0.5
b=pd.read_pickle(f'{S}/of_bars5.pkl'); D=pd.read_pickle(f'{S}/of_daily.pkl')
P=D.shift(1)  # včerejší úrovně
b['t']=b.index.time; T=lambda s:pd.Timestamp(s).time()
R=[]
def rec(h,name,pnl,dates,extra=''):
    p=pd.Series(np.asarray(pnl,float),index=pd.to_datetime(dates)).dropna()
    if len(p)<30: R.append(dict(h=h,var=name,n=len(p))); return
    y=p.groupby(p.index.year).mean()
    R.append(dict(h=h,var=name,n=len(p),pts=p.mean(),t=p.mean()/p.std()*np.sqrt(len(p)),win=(p>0).mean(),
                  roky_kladne=f'{(y>0).sum()}/{len(y)}',pozn=extra))
days={d:g for d,g in b.groupby('sday')}
def fwd_close(g,i):  # z close baru i do close 15:55 baru
    return g.close.iloc[-1]-g.close.iloc[i]
def first_touch(g,i,lvl_hi,lvl_lo):
    """od baru i: co se dotkne dřív – horní nebo dolní úroveň (1/-1/0)"""
    h=g.high.values[i+1:]; l=g.low.values[i+1:]
    th=np.argmax(h>=lvl_hi) if (h>=lvl_hi).any() else 10**9; tl=np.argmax(l<=lvl_lo) if (l<=lvl_lo).any() else 10**9
    if th==tl==10**9: return 0
    return 1 if th<tl else (-1 if tl<th else -1)  # stejný bar -> konzervativně proti
# ================= MARKET PROFILE =================
# H1: otevření vůči včerejší value area -> směr dne (open->close)
x=pd.DataFrame({'o':D.o,'c':D.c,'vah':P.vah,'val':P.val}).dropna()
for name,m,dr in [('open nad VAH -> long do close',x.o>x.vah,1),('open pod VAL -> short do close',x.o<x.val,-1),
                  ('open uvnitř VA -> long (drift)',(x.o<=x.vah)&(x.o>=x.val),1)]:
    s=x[m]; rec('H1 open vs VA',name,dr*(s.c-s.o)-COST,s.index)
# H2: 80% pravidlo – open mimo VA, 30min close zpět uvnitř do 12:00 -> cíl druhá hrana, symetrický SL
out=[];dts=[]
for d,g in days.items():
    if d not in P.index or np.isnan(P.loc[d,'vah']): continue
    vah,val=P.loc[d,'vah'],P.loc[d,'val']; o=g.open.iloc[0]
    if val<=o<=vah: continue
    g30=g.close.resample('30min').last(); 
    for ts,cl in g30.items():
        if ts.time()>T('11:30'): break
        if val<cl<vah:
            i=g.index.get_indexer([ts+pd.Timedelta(minutes=25)])[0]
            if i<0: break
            dr=-1 if o>vah else 1; tgt=val if dr<0 else vah; dist=abs(tgt-cl)
            ft=first_touch(g,i,cl+dist,cl-dist)
            pnl=(dist if ft==dr else (-dist if ft==-dr else dr*fwd_close(g,i)))-COST
            out.append(pnl/dist if dist>0 else np.nan); dts.append(d); break
rec('H2 80% pravidlo','re-entry do VA -> druhá hrana (v R, symetrický SL)',out,dts,'null = 0 R')
# H3: magnet včerejšího POC – P(dotyk) vs zrcadlová úroveň
hit=[];mir=[];dts=[]
for d,g in days.items():
    if d not in P.index or np.isnan(P.loc[d,'poc']): continue
    o=g.open.iloc[0]; poc=P.loc[d,'poc']; dist=abs(poc-o)
    if dist<2: continue
    mirror=o-(poc-o)
    t_poc=((g.high>=poc)&(g.low<=poc)).any(); t_mir=((g.high>=mirror)&(g.low<=mirror)).any()
    hit.append(t_poc); mir.append(t_mir); dts.append(d)
hit,mir=np.array(hit),np.array(mir); diff=hit.astype(float)-mir
R.append(dict(h='H3 POC magnet',var=f'P(dotyk včer. POC)={hit.mean():.2f} vs zrcadlo {mir.mean():.2f}',n=len(hit),
              pts=np.nan,t=diff.mean()/diff.std()*np.sqrt(len(diff)),win=np.nan,roky_kladne='',pozn='t rozdílu pravděpodobností'))
# H4: průraz IB + potvrzení deltou
res={'agree':[],'disagree':[]};dd={'agree':[],'disagree':[]}
for d,g in days.items():
    ib=g[g.t<T('10:30')]; rest=np.flatnonzero((g.t>=T('10:30'))&(g.t<=T('14:00')))
    if len(ib)<10 or not len(rest): continue
    ibh,ibl=ib.high.max(),ib.low.min()
    for i in rest:
        dr=1 if g.close.iloc[i]>ibh else (-1 if g.close.iloc[i]<ibl else 0)
        if dr:
            k='agree' if np.sign(g.cvd.iloc[i])==dr else 'disagree'
            res[k].append(dr*fwd_close(g,i)-COST); dd[k].append(d); break
rec('H4 IB průraz','close za IB + CVD souhlasí -> do close',res['agree'],dd['agree'])
rec('H4 IB průraz','close za IB + CVD nesouhlasí -> do close',res['disagree'],dd['disagree'])
# H5: úzký IB -> rozšíření (směr neurčen, jen informace o range)
x=[]
for d,g in days.items():
    ib=g[g.t<T('10:30')]
    if len(ib)<10: continue
    x.append((d,ib.high.max()-ib.low.min(),g.high.max()-g.low.min()))
x=pd.DataFrame(x,columns=['d','ib','day']).set_index('d'); x['ibr']=x.ib/x.ib.rolling(20).mean().shift(1); x=x.dropna()
q=pd.qcut(x.ibr,5); ext=(x.day/x.ib).groupby(q,observed=True).mean()
R.append(dict(h='H5 IB šířka',var='násobek IB, o který se den rozšíří: '+', '.join(f'{v:.2f}' for v in ext.values)+' (úzký→široký IB)',n=len(x),pozn='jen range, ne směr'))
# ================= VWAP =================
# H6: strana VWAP v 10:30 -> směr zbytku dne
for tchk in ('10:30','11:30'):
    pn=[];dts=[]
    for d,g in days.items():
        i=np.flatnonzero(g.t==T(tchk))
        if not len(i): continue
        i=i[0]; dr=np.sign(g.close.iloc[i]-g.vwap.iloc[i])
        if dr: pn.append(dr*fwd_close(g,i)-COST); dts.append(d)
    rec('H6 VWAP strana',f'v {tchk} na straně VWAP -> do close',pn,dts)
# H7: první pullback na VWAP v trendu (VWAP stoupá/klesá 30 min)
pn=[];dts=[]
for d,g in days.items():
    idx=np.flatnonzero((g.t>=T('10:30'))&(g.t<=T('14:30')))
    for i in idx:
        slope=g.vwap.iloc[i]-g.vwap.iloc[i-6] if i>=6 else 0
        prev_above=g.close.iloc[i-1]>g.vwap.iloc[i-1]
        if slope>0 and prev_above and g.low.iloc[i]<=g.vwap.iloc[i]<=g.high.iloc[i]:
            pn.append(g.close.iloc[-1]-g.vwap.iloc[i]-COST); dts.append(d); break
        if slope<0 and not prev_above and g.low.iloc[i]<=g.vwap.iloc[i]<=g.high.iloc[i]:
            pn.append(g.vwap.iloc[i]-g.close.iloc[-1]-COST); dts.append(d); break
rec('H7 VWAP pullback','1. dotyk VWAP ve směru sklonu -> do close (vstup limitkou na VWAP)',pn,dts)
# H8: fade 2σ pásma
for k in (2.0,2.5):
    pn=[];pn60=[];dts=[]
    for d,g in days.items():
        idx=np.flatnonzero((g.t>=T('10:30'))&(g.t<=T('15:00')))
        for i in idx:
            z=(g.close.iloc[i]-g.vwap.iloc[i])/g.vwap_sd.iloc[i] if g.vwap_sd.iloc[i]>0 else 0
            if abs(z)>=k:
                dr=-np.sign(z); j=min(i+12,len(g)-1)
                pn.append(dr*fwd_close(g,i)-COST); pn60.append(dr*(g.close.iloc[j]-g.close.iloc[i])-COST); dts.append(d); break
    rec('H8 VWAP ±σ fade',f'close za {k}σ -> fade do close',pn,dts); rec('H8 VWAP ±σ fade',f'close za {k}σ -> fade 60 min',pn60,dts)
# ================= DELTA =================
# H9: divergence CVD na novém high/low dne (po 11:00)
pn=[];dts=[]
for d,g in days.items():
    h=g.high.values; l=g.low.values; cvd=g.cvd.values; tt=g.t.values
    for i in range(12,len(g)-3):
        if tt[i]<T('11:00') or tt[i]>T('15:00'): continue
        prev_hi=h[:i].max(); j=int(np.argmax(h[:i]))
        if h[i]>prev_hi and cvd[i]<cvd[j]:
            pn.append(-(fwd_close(g,i))-COST); dts.append(d); break
        prev_lo=l[:i].min(); j=int(np.argmin(l[:i]))
        if l[i]<prev_lo and cvd[i]>cvd[j]:
            pn.append(fwd_close(g,i)-COST); dts.append(d); break
rec('H9 CVD divergence','nové high/low dne bez potvrzení CVD -> fade do close',pn,dts)
# H10: absorpce – extrémní delta baru, cena se nepohne (nebo jde proti)
b['dz']=(b.delta-b.groupby('sday').delta.transform(lambda s:s.rolling(24,min_periods=12).mean().shift(1)))/b.groupby('sday').delta.transform(lambda s:s.rolling(24,min_periods=12).std().shift(1))
b['move']=b.close-b.open
pn=[];pn30=[];dts=[]
for d,g in b[(b.t>=T('10:00'))&(b.t<=T('15:00'))].groupby('sday'):
    gg=days[d]
    for ts,row in g.iterrows():
        if abs(row.dz)>=3 and np.sign(row.move)!=np.sign(row.delta):
            i=gg.index.get_loc(ts); dr=-np.sign(row.delta); j=min(i+6,len(gg)-1)
            pn.append(dr*fwd_close(gg,i)-COST); pn30.append(dr*(gg.close.iloc[j]-gg.close.iloc[i])-COST); dts.append(d); break
rec('H10 absorpce','|Δz|≥3, cena proti deltě -> proti deltě do close',pn,dts)
rec('H10 absorpce','|Δz|≥3, cena proti deltě -> proti deltě 30 min',pn30,dts)
# H11: delta + cena souhlasí silně v prvních 30 min -> pokračování
pn=[];dts=[]
for d,g in days.items():
    i=np.flatnonzero(g.t==T('09:55'))
    if not len(i): continue
    i=i[0]; mv=g.close.iloc[i]-g.open.iloc[0]; cv=g.cvd.iloc[i]
    if np.sign(mv)==np.sign(cv) and mv!=0: pn.append(np.sign(mv)*fwd_close(g,i)-COST); dts.append(d)
rec('H11 delta+cena 1. půlhodina','cena i CVD stejným směrem -> pokračování do close',pn,dts)
# ================= SWING (denní) =================
nd=D.c.shift(-1)-D.c; nd3=D.c.shift(-3)-D.c; nod=D.c.shift(-1)-D.o.shift(-1)
x=pd.DataFrame({'c':D.c,'o':D.o,'delta':D.delta,'nd':nd,'nd3':nd3}).dropna()
m=(x.c>x.o)&(x.delta<0); rec('S1 denní divergence delty','růst dne + záporná delta -> short 1 den',-x.nd[m]-COST,x.index[m])
m=(x.c<x.o)&(x.delta>0); rec('S1 denní divergence delty','pokles dne + kladná delta -> long 1 den',x.nd[m]-COST,x.index[m])
m=(x.c<x.o)&(x.delta>0); rec('S1 denní divergence delty','pokles dne + kladná delta -> long 3 dny',x.nd3[m]-COST,x.index[m])
va=pd.DataFrame({'vah':D.vah,'val':D.val,'pvah':P.vah,'pval':P.val,'nd':nd,'nd3':nd3}).dropna()
up=(va.val>va.pval)&(va.vah>va.pvah); dn=(va.val<va.pval)&(va.vah<va.pvah)
up2=up&up.shift(1,fill_value=False); dn2=dn&dn.shift(1,fill_value=False)
rec('S2 migrace value','2 dny VA výš -> long 1 den',va.nd[up2]-COST,va.index[up2]); rec('S2 migrace value','2 dny VA níž -> short 1 den',-va.nd[dn2]-COST,va.index[dn2])
rec('S2 migrace value','2 dny VA níž -> long 3 dny (reverze)',va.nd3[dn2]-COST,va.index[dn2])
ca=pd.DataFrame({'c':D.c,'vah':D.vah,'val':D.val,'nd':nd}).dropna()
rec('S3 close vs VA','close nad VAH -> long 1 den',ca.nd[ca.c>ca.vah]-COST,ca.index[ca.c>ca.vah])
rec('S3 close vs VA','close pod VAL -> long 1 den (reverze)',ca.nd[ca.c<ca.val]-COST,ca.index[ca.c<ca.val])
od=pd.DataFrame({'ond':D.on_delta,'oc':D.c-D.o}).dropna()
rec('S4 overnight delta','znaménko overnight delty -> RTH open->close',np.sign(od.ond)*od.oc-COST,od.index)
wk=D.index.to_period('W'); wv=(D.vwap_close*D.vol).groupby(wk).cumsum()/D.vol.groupby(wk).cumsum()
x=pd.DataFrame({'c':D.c,'wv':wv,'nd':nd}).dropna()
rec('S5 týdenní VWAP','close nad týdenním VWAP -> long 1 den',x.nd[x.c>x.wv]-COST,x.index[x.c>x.wv])
rec('S5 týdenní VWAP','close pod týdenním VWAP -> long 1 den (reverze)',x.nd[x.c<x.wv]-COST,x.index[x.c<x.wv])
# benchmark: long drift
rec('BENCHMARK','buy & hold 1 den (každý den)',nd.dropna()-COST,nd.dropna().index)
rec('BENCHMARK','long open->close každý den',(D.c-D.o)-COST,D.index)
out=pd.DataFrame(R); pd.set_option('display.width',260); pd.set_option('display.max_colwidth',80)
print(out.round(3).to_string(index=False)); out.to_csv(os.environ.get('OUT','reports/es_orderflow')+'/hypotezy.csv',index=False)
