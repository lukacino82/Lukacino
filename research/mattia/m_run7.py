import sys, pickle
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import numpy as np, pandas as pd
from families import *
from base import summarize
G=pickle.load(open('/tmp/claude-0/data/m_grid.pkl','rb'))
res=pickle.load(open('/tmp/claude-0/data/m_res1.pkl','rb'))
r=bh(G)
pc=pd.Series(G.pC,index=G.days)
def tr2daily(t,cost=0.5):
    s=(t.pnl-cost).groupby(t.date).sum()
    return (s/pc.reindex(s.index)).reindex(G.days).fillna(0)
S={}
S['B&H']=r
S['Vol-managed B&H']=exposure_overlays(G)['Vol-managed B&H (cap 2x)'][0]*r
w=crisis_allocator(G,dd_thr=-0.03,ll=3,layer=0.5,hold=60,max_layers=2).shift().fillna(1)
S['Crisis allocator (-3%, 0.5x, 2 vrstvy)']=w*r
S['S1 Vault Break']=tr2daily(res['S1'])
S['S2 VWAP Pullback']=tr2daily(res['S2'])
S['S3 Overnight Bias']=tr2daily(res['S3'])
S['Noise-area momentum L/S']=noise_momentum(G)[0]
S['Turn of month']=turn_of_month(G)
S['Pre-FOMC']=pre_fomc(G).reindex(G.days).fillna(0)
S['IBS<0.2 bull']=ibs_bull(G)
df=pd.DataFrame(S).fillna(0)
df.to_parquet('/tmp/claude-0/data/daily_series.parquet')
print(df.corr().round(2).to_string())
# Combined books: core + overlays (overlays add their daily % on top of core capital)
def perf(x):
    eq=(1+x).cumprod(); yrs=len(x)/252; c=eq.iloc[-1]**(1/yrs)-1; dd=(eq/eq.cummax()-1).min()
    return dict(CAGR=round(c*100,2),SR=round(x.mean()/x.std()*np.sqrt(252),2),DD=round(dd*100,1),MAR=round(c/abs(dd),2),vol=round(x.std()*np.sqrt(252)*100,1))
books={'B&H':df['B&H'],
 'Vol-managed':df['Vol-managed B&H'],
 'Vol-managed + Noise + S3 + Pre-FOMC': df['Vol-managed B&H']+df['Noise-area momentum L/S']+df['S3 Overnight Bias']+df['Pre-FOMC'],
 'Crisis allocator':df['Crisis allocator (-3%, 0.5x, 2 vrstvy)'],
 'Allocator + Noise + S3':df['Crisis allocator (-3%, 0.5x, 2 vrstvy)']+df['Noise-area momentum L/S']+df['S3 Overnight Bias'],
 'Mattia S1+S2+S3':df['S1 Vault Break']+df['S2 VWAP Pullback']+df['S3 Overnight Bias'],
}
rows=[]
for k,x in books.items():
    d={'book':k,**perf(x)}
    for lab,a,z in [('PRE','2008','2017-12-31'),('IS','2018','2022-12-31'),('OOS','2023','2027')]:
        xx=x[a:z]; d[lab+'_SR']=round(xx.mean()/xx.std()*np.sqrt(252),2)
    # B&H scaled to the same volatility
    sc=x.std()/r.std(); d['B&H same vol CAGR']=perf(r*sc)['CAGR']; d['B&H same vol DD']=perf(r*sc)['DD']
    rows.append(d)
pd.set_option('display.width',260); print(pd.DataFrame(rows).to_string())
