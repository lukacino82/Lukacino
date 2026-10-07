import sys, time, pickle
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import numpy as np, pandas as pd
from base import Bars, summarize
from strategies import *
t=time.time(); B=Bars(); print('bars', time.time()-t, len(B.days), len(B.D))
pickle.dump(B, open('/tmp/claude-0/data/m_bars.pkl','wb'))
a1=adx_1min(B); a15,i15=adx_15min(B); np.save('/tmp/claude-0/data/adx1.npy',a1); np.save('/tmp/claude-0/data/adx15.npy',a15); np.save('/tmp/claude-0/data/idx15.npy',i15)
print('adx', time.time()-t)
res={}
res['S1']=s1_vault_break(B); print('s1', time.time()-t)
res['S2']=s2_vwap_pullback(B,a1); print('s2', time.time()-t)
res['S3']=s3_overnight_bias(B,a15,i15); print('s3', time.time()-t)
pickle.dump(res, open('/tmp/claude-0/data/m_res1.pkl','wb'))
pd.set_option('display.width',200)
for k,v in res.items():
    print(k); print(pd.DataFrame(summarize(v)).T.round(2))
