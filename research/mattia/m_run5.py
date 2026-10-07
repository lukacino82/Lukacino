import sys, pickle
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import numpy as np, pandas as pd
from families import *
G=pickle.load(open('/tmp/claude-0/data/m_grid.pkl','rb'))
r=bh(G)
def perf(x):
    eq=(1+x).cumprod(); yrs=len(x)/252
    return dict(CAGR=round((eq.iloc[-1]**(1/yrs)-1)*100,2), SR=round(x.mean()/x.std()*np.sqrt(252),2), DD=round((eq/eq.cummax()-1).min()*100,1), MAR=round(((eq.iloc[-1]**(1/yrs)-1))/abs((eq/eq.cummax()-1).min()),2))
rows=[]
rows.append(dict(name='B&H 1x',avg_w=1,**perf(r)))
for args in [dict(),dict(layer=0.5),dict(dd_thr=-0.05),dict(max_layers=2),dict(hold=40)]:
    w=crisis_allocator(G,**args); x=w.shift().fillna(1)*r
    aw=w.mean(); rows.append(dict(name=f'Crisis allocator {args}',avg_w=round(aw,2),**perf(x)))
    rows.append(dict(name=f'  B&H constant {aw:.2f}x',avg_w=round(aw,2),**perf(aw*r)))
    vm_w=exposure_overlays(G)['Vol-managed B&H (cap 2x)'][0]
    sc=aw/vm_w.mean(); rows.append(dict(name=f'  Vol-managed scaled to {aw:.2f}x',avg_w=round(aw,2),**perf((vm_w*sc).clip(0,4)*r)))
print(pd.DataFrame(rows).to_string())
