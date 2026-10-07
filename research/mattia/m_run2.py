import sys, pickle
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import numpy as np, pandas as pd
from base import Bars, summarize
from strategies import *
B=pickle.load(open('/tmp/claude-0/data/m_bars.pkl','rb'))
a1=np.load('/tmp/claude-0/data/adx1.npy'); a15=np.load('/tmp/claude-0/data/adx15.npy'); i15=np.load('/tmp/claude-0/data/idx15.npy')
res=pickle.load(open('/tmp/claude-0/data/m_res1.pkl','rb'))
def row(name,t,cost=0.5):
    s=summarize(t,cost); r={'var':name}
    for p in s: r[p+'_n']=s[p].get('n'); r[p+'_exp']=round(s[p].get('exp',np.nan),2)
    r['pf']=round(s['ALL'].get('pf',np.nan),2); r['t']=round(s['ALL'].get('t',np.nan),2); return r
rows=[]
s3=res['S3']
rows.append(row('S3 base',s3)); rows.append(row('S3 gross (cost 0)',s3,0)); rows.append(row('S3 cost 1.0',s3,1.0))
rows.append(row('S3 long only',s3[s3.side>0])); rows.append(row('S3 short only',s3[s3.side<0]))
for k_sl,rr in [(0.2,3),(0.3,2),(0.3,4),(0.4,3),(0.3,1.5),(0.5,2)]:
    rows.append(row(f'S3 SL{k_sl} RR{rr}',s3_overnight_bias(B,a15,i15,k_sl=k_sl,rr=rr)))
rows.append(row('S3 no ADX',s3_overnight_bias(B,a15,i15,adx_min=0)))
rows.append(row('S3 ADX>25',s3_overnight_bias(B,a15,i15,adx_min=25)))
rows.append(row('S3 no bias (ORB both)',s3_overnight_bias(B,a15,i15,third=1.01)))
rows.append(row('S3 bias quarter',s3_overnight_bias(B,a15,i15,third=0.25)))
rows.append(row('S3 bias 40%',s3_overnight_bias(B,a15,i15,third=0.4)))
rows.append(row('S3 exit 16:00',s3_overnight_bias(B,a15,i15,exit_at=16*60)))
s1=res['S1']
rows.append(row('S1 base',s1)); rows.append(row('S1 gross',s1,0))
for k,tp,sl in [(0.2,0.13,0.25),(0.4,0.13,0.25),(0.3,0.2,0.2),(0.3,0.3,0.3),(0.3,0.1,0.3),(0.5,0.3,0.3)]:
    rows.append(row(f'S1 k{k} tp{tp} sl{sl}',s1_vault_break(B,k=k,tp_atr=tp,sl_atr=sl)))
rows.append(row('S1 1 trade/day',s1_vault_break(B,max_trades=1)))
rows.append(row('S1 no VWAP',s1_vault_break(B,use_vwap=False)))
rows.append(row('S1 pts TP10 SL19',s1_vault_break(B,tp_pts=10,sl_pts=19)))
s2=res['S2']; rows.append(row('S2 gross',s2,0))
rows.append(row('S2 RTH vwap',s2_vwap_pullback(B,a1,anchor=570)))
pd.set_option('display.width',250); print(pd.DataFrame(rows).to_string())
