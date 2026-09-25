"""Denní tabulka z volume barů ES (Excel, 07/2016–07/2026) pro brainstorming hypotéz.

Čas baru = začátek baru (ET). „Cena v čase T“ = close posledního baru, který začal před T
(stejně jako by ji viděla Sierra studie v čase T). Ceny jsou back-adjustované.

Sloupce (index = kalendářní datum obchodního dne):
  o930, p1000, p1030, p1530, c1558, c1600      ceny v daných časech
  h, l (09:30–15:58), h30, l30 (09:30–10:00)   RTH extrémy
  on_h, on_l, p0300                             overnight 18:00 předchozího dne – 09:30
  d_rth, d_on                                   delta (ask − bid objem) RTH a overnight
  i0, i1                                        rozsah indexů RTH barů (09:30–15:58)

python analysis/brainstorm/features.py <bary .pkl> <výstup .pkl>
"""
import sys
import numpy as np, pandas as pd

df = pd.read_pickle(sys.argv[1])
TS = df.index
sec = (TS.hour * 3600 + TS.minute * 60 + TS.second).values
O, H, L, C = (df[k].values for k in ("open", "high", "low", "close"))
DEL = (df.ask - df.bid).values.astype(float)
# obchodní den: seance od 18:00 předchozího dne do 17:00
sday = (TS + pd.Timedelta(hours=6)).normalize()
S = lambda h, m=0: h * 3600 + m * 60

rows = []
for d, idx in pd.Series(np.arange(len(df)), index=sday).groupby(level=0):
    ii = idx.values; cal = TS[ii].normalize() == d          # bary kalendářního dne d
    s = np.where(cal, sec[ii], sec[ii] - 86400)             # večerní bary předchozího dne < 0
    rth = ii[(s >= S(9, 30)) & (s < S(15, 58))]
    if len(rth) < 20 or s.max() < S(15, 45): continue
    def px(t):
        k = ii[s < t]
        return C[k[-1]] if len(k) else np.nan
    first = ii[s >= S(9, 30)][0]
    on = ii[(s < S(9, 30))]
    r30 = ii[(s >= S(9, 30)) & (s < S(10))]
    rows.append(dict(d=d, o930=O[first], p1000=px(S(10)), p1030=px(S(10, 30)), p1530=px(S(15, 30)),
                     c1558=px(S(15, 58)), c1600=px(S(16)), p0300=px(S(3)),
                     h=H[rth].max(), l=L[rth].min(), h30=H[r30].max() if len(r30) else np.nan,
                     l30=L[r30].min() if len(r30) else np.nan,
                     on_h=H[on].max() if len(on) else np.nan, on_l=L[on].min() if len(on) else np.nan,
                     d_rth=DEL[rth].sum(), d_on=DEL[on].sum() if len(on) else np.nan,
                     i0=rth[0], i1=rth[-1]))
F = pd.DataFrame(rows).set_index("d")
F.to_pickle(sys.argv[2])
print(len(F), F.index[0], F.index[-1]); print(F.tail(3).round(2).T)
