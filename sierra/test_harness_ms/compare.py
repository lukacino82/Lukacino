"""Srovnání virtuálních obchodů studie (emulace) s obchody z výzkumu (analysis/brainstorm, buy_weakness)."""
import sys, pandas as pd, numpy as np
S = sys.argv[1]
F = pd.read_pickle(f'{S}/bs_daily.pkl'); dates = F.index; start = int(dates[201].strftime('%Y%m%d'))
T5 = pd.read_pickle(f'{S}/bs/_trades_kolo5_base.pkl'); TB = pd.read_pickle('reports/buy_weakness/_trades.pkl')
ref = {'RSI': T5['1 RSI(2) | RSI(2) < 10 nad MA200 → do close > MA5 (max 10)'],
       'LC': T5['2 Série poklesů | 3 nižší close → do 1. vyššího close (max 10)'],
       'CAP': T5['3 Kapitulační objem | pokles a objem > 1.6× průměr 20 dní → do close > včerejší high (max 5)'],
       'ABS': T5['4 Absorpce short | pokles a delta > 0 → short 1 den/dny']}
d8 = lambda k: int(dates[k].strftime('%Y%m%d'))
def load(path):
    L = [l.strip().split('|') for l in open(path)]
    t = pd.DataFrame(L, columns='tag sys ed xd e x dir q why'.split())
    t[['ed', 'xd', 'dir', 'q']] = t[['ed', 'xd', 'dir', 'q']].astype(int); t[['e', 'x']] = t[['e', 'x']].astype(float)
    t['pts'] = (t.x - t.e) * t.dir - 0.5
    return t
for n in sys.argv[2:]:
    t = load(f'{S}/ms_{n}.txt')
    if n == 'VAL':
        r = TB['VAL swing (výzkum: bez stopu, max 10 dní)']
        R = pd.DataFrame({'ed': r.entry_d.dt.strftime('%Y%m%d').astype(int), 'xd': r.exit_d.dt.strftime('%Y%m%d').astype(int), 'pts': r.pts.values}); s = t
    else:
        R = pd.DataFrame([(d8(k), d8(j), p) for k, j, p, dd in ref[n]], columns=['ed', 'xd', 'pts']); s = t[t.ed >= start]
    m = s.merge(R, on=['ed', 'xd'], how='outer', indicator=True, suffixes=('_ms', '_ref')); both = m[m._merge == 'both']
    print(f"{n:4s} studie {len(s):4d} obch {s.pts.mean():6.2f} b. | výzkum {len(R):4d} obch {R.pts.mean():6.2f} b. | "
          f"shodné vstup+výstup {len(both)} ({len(both)/max(len(R),1)*100:.0f} %) | max rozdíl bodů u shodných {np.abs(both.pts_ms - both.pts_ref).max():.3f}")
