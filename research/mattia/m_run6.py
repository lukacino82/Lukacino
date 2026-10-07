import sys, pickle, itertools
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import numpy as np, pandas as pd
from families import *
G=pickle.load(open('/tmp/claude-0/data/m_grid.pkl','rb'))
r=bh(G)
P=[('PRE','2008','2017-12-31'),('IS','2018','2022-12-31'),('OOS','2023','2027')]
def alpha_t(x,b):
    X=np.c_[np.ones(len(b)),b.values]; be=np.linalg.lstsq(X,x.values,rcond=None)[0]; res=x.values-X@be
    return be[0]/np.sqrt(res.var(ddof=2)/len(x)), be[1]
rows=[]
grid=list(itertools.product([-0.02,-0.03,-0.05,-0.08],[2,3,4],[0.5,0.8],[20,40,60],[2,4]))
for dd,ll,lay,hold,ml in grid:
    w=crisis_allocator(G,dd_thr=dd,ll=ll,layer=lay,hold=hold,max_layers=ml).shift().fillna(1)
    x=w*r; aw=w.mean()
    d=dict(dd=dd,ll=ll,layer=lay,hold=hold,maxl=ml,avg_w=round(aw,2))
    t,be=alpha_t(x,r); d['alpha_t']=round(t,2)
    for lab,a,z in P:
        xx=x[a:z]; bb=r[a:z]; ww=w[a:z].mean()
        d[lab+'_SR']=round(xx.mean()/xx.std()*np.sqrt(252),2)
        d[lab+'_SR_BH']=round(bb.mean()/bb.std()*np.sqrt(252),2)
        # excess over constant leverage with same average exposure in that period
        d[lab+'_exc%']=round((xx.mean()-ww*bb.mean())*252*100,2)
    rows.append(d)
df=pd.DataFrame(rows)
pd.set_option('display.width',250)
print('configs',len(df),' SR>BH all 3 periods:',((df.PRE_SR>df.PRE_SR_BH)&(df.IS_SR>df.IS_SR_BH)&(df.OOS_SR>df.OOS_SR_BH)).mean().round(2),
      ' excess>0 all periods:',((df['PRE_exc%']>0)&(df['IS_exc%']>0)&(df['OOS_exc%']>0)).mean().round(2))
print(df.describe().round(2).T[['mean','min','50%','max']])
print(df.sort_values('alpha_t',ascending=False).head(10).to_string())
df.to_csv('/tmp/claude-0/data/alloc_grid.csv',index=False)
