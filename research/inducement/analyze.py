import numpy as np, pandas as pd
D='/tmp/claude-0/data/idm/'
def load(s):
    E=pd.read_parquet(D+f'E_{s}.parquet'); T=pd.read_parquet(D+f'T_{s}.parquet')
    E['year']=pd.to_datetime(E.gday).dt.year; E['wk']=pd.to_datetime(E.gday).dt.to_period('W').astype(str)
    T=T.join(E[['typ','side','win','trend','relvol','konfluence','year','wk','atr']],on='e')
    return E,T
def per(y): return 'A 08-15' if y<=2015 else ('B 16-20' if y<=2020 else 'C 21-26')
def cl_t(df,col):
    # week-cluster t of mean
    g=df.groupby('wk')[col].agg(['sum','count']); n=g['count'].sum(); m=g['sum'].sum()/n
    r=g['sum']-m*g['count']; se=np.sqrt((r**2).sum())/n
    return m,se,(m/se if se>0 else np.nan),int(n)
out={}
sets={s:load(s) for s in ['real','pl1','pl2','pl3']}
rows=[]
for s,(E,T) in sets.items():
    for D_ in ['0.1','0.2','0.4']:
        e=E[E[f'race{D_}']!=0].copy(); e['fail']=(e[f'race{D_}']==-1)*1.0
        # drift balanced: avg of side groups
        a=e[e.side==1].fail.mean(); b=e[e.side==-1].fail.mean()
        m,se,t,n=cl_t(e.assign(x=e.fail-0.5),'x')
        rows.append(dict(set=s,D=D_,n=n,fail_up_sweep=a,fail_down_sweep=b,fail_bal=(a+b)/2,t_raw=t))
R1=pd.DataFrame(rows); print(R1.round(4)); R1.to_csv('out/A_race_total.csv',index=False)
E,T=sets['real']
# race by type & window & trend, D=0.2
def race_tab(E,by,D_='0.2'):
    e=E[E[f'race{D_}']!=0].copy(); e['fail']=(e[f'race{D_}']==-1)*1.0
    g=e.groupby(by+['side']).fail.agg(['mean','count']).unstack('side')
    r=pd.DataFrame({'n':g['count'].sum(axis=1),'fail_bal':g['mean'].mean(axis=1)}); return r
for by in (['typ'],['win'],['trend'],['konfluence']):
    r=race_tab(E,by); rp=pd.concat([race_tab(sets[s][0],by) for s in ['pl1','pl2','pl3']]).groupby(level=list(range(len(by)))).fail_bal.mean()
    r['placebo']=rp; r['diff_pp']=(r.fail_bal-r.placebo)*100; print(r.round(4)); r.to_csv(f"out/A_race_{by[0]}.csv")
# trades reversal
def tt(T,kind='reverzni'):
    x=T[(T.kind==kind)&T.good]
    return x
res=[]
for s,(E_,T_) in sets.items():
    x=tt(T_)
    for (typ,W,R),g in x.groupby(['typ','W','R']):
        res.append(dict(set=s,typ=typ,W=W,R=R,n=len(g),win=(g.res==1).mean(),null=g.null_win.iloc[0],Rnet=g.Rnet.mean()))
RT=pd.DataFrame(res); RT.to_csv('out/B_trade_cfg.csv',index=False)
rt=RT[RT.set=='real']; print('real cfgs',len(rt),'mean Rnet',rt.Rnet.mean(),'share>0',(rt.Rnet>0).mean())
pl=RT[RT.set!='real']; print('placebo mean Rnet',pl.Rnet.mean(),'share>0',(pl.Rnet>0).mean())
# overall by kind/R/W
for kind in ['reverzni','akceptace']:
    for s in ['real','pl1']:
        x=tt(sets[s][1],kind); g=x.groupby(['W','R']).agg(n=('res','size'),win=('res',lambda v:(v==1).mean()),null=('null_win','mean'),Rnet=('Rnet','mean'))
        print(kind,s);print(g.round(4))
# by period for reversal W=30 R=2
x=tt(T); x=x.assign(per=x.year.map(per)); 
g=x.groupby(['per','W','R']).agg(n=('res','size'),win=('res',lambda v:(v==1).mean()),null=('null_win','mean'),Rnet=('Rnet','mean'));print(g.round(4)); g.to_csv('out/B_period.csv')
# significance scan: t per cfg (typ,win,W,R) with week clusters; count |t|>2 vs placebo
def scan(T_):
    x=tt(T_); rr=[]
    for k,g in x.groupby(['typ','win','W','R']):
        if len(g)<300: continue
        m,se,t,n=cl_t(g.assign(x=g.Rnet),'x'); rr.append((k,n,m,t))
    return pd.DataFrame([(*k,n,m,t) for k,n,m,t in rr],columns=['typ','win','W','R','n','Rnet','t'])
S=scan(T); S.to_csv('out/C_scan_real.csv',index=False)
Sp=pd.concat([scan(sets[s][1]) for s in ['pl1','pl2','pl3']])
print('scan real n',len(S),'|t|>2',(S.t.abs()>2).mean(),'t>2',(S.t>2).mean(),'t<-2',(S.t<-2).mean(),'; placebo',(Sp.t.abs()>2).mean(),(Sp.t>2).mean(),(Sp.t<-2).mean())
print(S.sort_values('t').tail(8).round(3))
# qualifiers on reversal W=30,R=2
x=tt(T); x=x[(x.W==30)&(x.R==2)]
for q,b in [('relvol',[0,1,2,4,1e9]),('konfluence',[-1,0,1,2,99]),('trend',None)]:
    k=pd.cut(x[q],b) if b else x[q]
    print(x.groupby(k,observed=True).agg(n=('res','size'),win=('res',lambda v:(v==1).mean()),Rnet=('Rnet','mean')).round(4))
# gross (before cost) and avg risk
print('avg risk pts',x.risk_pts.mean(),'Rnet',x.Rnet.mean(),'gross win',(x.res==1).mean(),'null',1/3)
