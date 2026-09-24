import pandas as pd,sys
t=pd.read_csv(sys.argv[1])
if len(t)==0: print('   no trades'); sys.exit()
t['pts']=(t.exit-t.entry)*t.dir-0.5
print('   n',len(t),'L/S',(t.dir>0).sum(),(t.dir<0).sum(),t.why.value_counts().to_dict(),'max/day',t.groupby('d').size().max(),
 'net $%.1fk'%(t.pts.sum()*50/1000),'overnight',(t.xd!=t.d).sum(), 'last entry h %.2f'%(t.t.max()/3600))
