"""Brainstorming: 11 rodin hypotéz na ES (volume bary 07/2016–07/2026), každá s mechanismem
a 2–4 variantami parametrů (kontrola plató). Vše po nákladech 0,5 b. na obchod.

Testy každé varianty:
  * t obchodu, kladné roky, 2016–2021 vs. 2022–2026 (mimo vzorek je jen „nové“ období,
    parametry jsou předem dané, ne optimalizované)
  * NULA: stejná pravidla v náhodné dny (bez podmínky), stejný počet obchodů, 2 000×
    → p = jak často náhoda vyjde stejně dobře. Tím se odečte drift i samotná mechanika výstupu.
  * ALFA: regrese denního P&L strategie na denní pohyb ES (close 15:58 → 15:58): alfa a její t.

python analysis/brainstorm/hypotheses.py <bary .pkl> <denní .pkl z features.py> <výstupní složka>
"""
import sys, os
import numpy as np, pandas as pd

BARS, DAILY, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(OUT, exist_ok=True)
COST = float(os.environ.get("COST", 0.5))
df = pd.read_pickle(BARS)
BO, BH, BL, BC, BV = (df[k].values for k in ("open", "high", "low", "close", "vol"))
BT = (df.index.hour * 3600 + df.index.minute * 60 + df.index.second).values
F = pd.read_pickle(DAILY)
N = len(F); dates = F.index
c = F[os.environ.get("CLOSE", "c1558")].values; o = F.o930.values; h = F.h.values; l = F.l.values
cp = np.r_[np.nan, c[:-1]]
atr = pd.Series(h - l).rolling(14).mean().shift(1).values
ma200 = pd.Series(c).rolling(200).mean().values; ma5 = pd.Series(c).rolling(5).mean().values
dlt = np.diff(c, prepend=np.nan); up, dn = np.clip(dlt, 0, None), np.clip(-dlt, 0, None)
au = pd.Series(up).ewm(alpha=.5, adjust=False).mean().values; ad = pd.Series(dn).ewm(alpha=.5, adjust=False).mean().values
rsi2 = 100 - 100 / (1 + au / np.where(ad == 0, 1e-9, ad))
ibs = (c - l) / np.where(h > l, h - l, np.nan)
mkt = np.r_[0, np.diff(c)]                      # denní pohyb trhu (body)
WARM = 201
ELIG = np.arange(WARM, N - 12)
month = dates.month.values
last_of_month = np.r_[month[1:] != month[:-1], True]

# ------------------------------------------------------------------ pricing jednotlivých obchodů
def hold_until(k, direction, exit_fn, max_hold):
    """Vstup c[k], výstup na c[j] v první den j>k, kdy exit_fn(j) je True, nebo po max_hold."""
    for j in range(k + 1, min(k + max_hold, N - 1) + 1):
        if exit_fn(j): break
    return direction * (c[j] - c[k]) - COST, j

def mtm(k, j, direction):
    """Denní přecenění close→close pro regresi (bez nákladů, ty se odečtou v den výstupu)."""
    return [(m, direction * (c[m] - c[m - 1])) for m in range(k + 1, j + 1)]

def gap_fade(k, rrr=2.0, side=0):
    """Gap 0,2–1,5 ATR proti včerejšímu close. V 10:00 cena zpět za open → vstup proti gapu,
    SL za extrémem 09:30–10:00, TP = RRR × riziko, jinak výstup 16:00."""
    g = o[k] - F.c1600.values[k - 1]
    if not (0.2 * atr[k] <= abs(g) <= 1.5 * atr[k]): return None
    d = -np.sign(g)
    if side and d != side: return None
    e = F.p1000.values[k]
    if d < 0 and not e < o[k]: return None
    if d > 0 and not e > o[k]: return None
    sl = F.h30.values[k] if d < 0 else F.l30.values[k]
    risk = abs(sl - e)
    if risk < 1: return None
    tp = e + d * rrr * risk
    i0, i1 = int(F.i0.values[k]), int(F.i1.values[k])
    ii = np.arange(i0, i1 + 1); ii = ii[BT[ii] >= 36000]
    for i in ii:
        if (d > 0 and BL[i] <= sl) or (d < 0 and BH[i] >= sl): return d * (sl - e) - COST
        if (d > 0 and BH[i] >= tp) or (d < 0 and BL[i] <= tp): return d * (tp - e) - COST
    return d * (F.c1600.values[k] - e) - COST

def vwap_rev(k, z=2.0, side=1):
    """10:30–15:00: close baru za VWAP ∓ z·σ → vstup proti, výstup na VWAP nebo 15:58."""
    i0, i1 = int(F.i0.values[k]), int(F.i1.values[k])
    tp_ = (BH[i0:i1 + 1] + BL[i0:i1 + 1] + BC[i0:i1 + 1]) / 3; v = BV[i0:i1 + 1]
    cv = np.cumsum(v); vw = np.cumsum(tp_ * v) / cv; sd = np.sqrt(np.maximum(np.cumsum(tp_ * tp_ * v) / cv - vw ** 2, 0))
    t = BT[i0:i1 + 1]
    for n in range(len(v)):
        if not (37800 <= t[n] < 54000): continue
        if side > 0 and BC[i0 + n] < vw[n] - z * sd[n]:
            e = BC[i0 + n]
            for m in range(n + 1, len(v)):
                if BH[i0 + m] >= vw[m]: return vw[m] - e - COST
            return c[k] - e - COST
        if side < 0 and BC[i0 + n] > vw[n] + z * sd[n]:
            e = BC[i0 + n]
            for m in range(n + 1, len(v)):
                if BL[i0 + m] <= vw[m]: return e - vw[m] - COST
            return e - c[k] - COST
    return None

# ------------------------------------------------------------------ definice hypotéz
# každá: (rodina, varianta, mechanismus, cond(k)->bool, trade(k)->(pnl, j, direction) nebo None)
def swing(direction, exit_fn, max_hold):
    return lambda k: (*hold_until(k, direction, exit_fn, max_hold), direction)
def one_day(direction):
    return lambda k: (direction * (c[k + 1] - c[k]) - COST, k + 1, direction)
def overnight(k):
    return (o[k + 1] - c[k] - COST, k + 1, 1)
def intraday(fn, **kw):
    def t(k):
        r = fn(k, **kw)
        return None if r is None else (r, k, 0)
    return t
def intraday_mom(k, thr=0.0, long_only=False):
    r1 = F.p1000.values[k] - F.c1600.values[k - 1]
    if abs(r1) < thr * atr[k] or r1 == 0: return None
    d = np.sign(r1)
    if long_only and d < 0: return None
    return d * (F.c1600.values[k] - F.p1530.values[k]) - COST
def on_low_reclaim(k, side=1):
    """Stop-run pod overnight low (nebo nad overnight high) v 09:30–10:00 a návrat zpět v 10:00."""
    if side > 0 and F.l30.values[k] < F.on_l.values[k] and F.p1000.values[k] > F.on_l.values[k]:
        return F.c1600.values[k] - F.p1000.values[k] - COST
    if side < 0 and F.h30.values[k] > F.on_h.values[k] and F.p1000.values[k] < F.on_h.values[k]:
        return F.p1000.values[k] - F.c1600.values[k] - COST
    return None
def down_streak(n):
    return lambda k: all(c[k - i] < c[k - i - 1] for i in range(n))
tom_k = {}
def tom(k, before=1, after=3):
    # vstup na close `before` obchodních dní před koncem měsíce, výstup na close `after`-tého dne nového měsíce
    return last_of_month[k + before] if k + before < N else False

H = []
for thr in (0.1, 0.2, 0.3):
    H.append(("A IBS nízký close v rámci dne", f"IBS < {thr} → long 1 den", "zavření u low = nucené prodeje na close, druhý den návrat",
              lambda k, thr=thr: ibs[k] < thr, one_day(1)))
for n in (2, 3, 4):
    H.append(("B Série poklesů", f"{n} nižší close → long do 1. vyššího close (max 10)", "vyčerpání prodejců",
              down_streak(n), swing(1, lambda j: c[j] > c[j - 1], 10)))
H.append(("C Noční držení", "každou noc close → open", "noční riziková prémie", lambda k: True, overnight))
H.append(("C Noční držení", "noc po poklesovém dni", "prémie + reverze", lambda k: c[k] < cp[k], overnight))
H.append(("C Noční držení", "noc po IBS < 0,3", "prémie + reverze", lambda k: ibs[k] < 0.3, overnight))
H.append(("C Noční držení", "noc nad MA200", "prémie v býčím režimu", lambda k: c[k] > ma200[k], overnight))
for thr, lo in ((0.0, False), (0.25, False), (0.0, True)):
    H.append(("D Intradenní momentum (Gao 2018)", f"směr 1. půlhodiny, 15:30–16:00{', |r1|>0,25 ATR' if thr else ''}{', jen long' if lo else ''}",
              "zajišťování opcí (gamma) a pozdní informovaní obchodníci", lambda k: True, intraday(intraday_mom, thr=thr, long_only=lo)))
for rrr, side in ((2.0, 0), (1.0, 0), (2.0, 1), (2.0, -1)):
    H.append(("E Gap fade s potvrzením", f"RRR {rrr:g}, {'oba směry' if side == 0 else ('jen long' if side > 0 else 'jen short')}",
              "přestřelení na openu, uzavírání gapu", lambda k: True, intraday(gap_fade, rrr=rrr, side=side)))
for z, side in ((2.0, 1), (2.5, 1), (2.0, -1), (2.5, -1)):
    H.append(("F VWAP ±zσ reverze", f"z = {z:g}, {'long pod VWAP' if side > 0 else 'short nad VWAP'}",
              "poskytování likvidity intradenně", lambda k: True, intraday(vwap_rev, z=z, side=side)))
for m in (1.25, 1.5, 2.0):
    H.append(("G Panický den", f"rozpětí > {m:g} ATR a IBS < 0,25 → long do close > včerejší high (max 5)",
              "kapitulace", lambda k, m=m: (h[k] - l[k]) > m * atr[k] and ibs[k] < 0.25,
              swing(1, lambda j: c[j] > h[j - 1], 5)))
for thr in (80, 90, 95):
    H.append(("H Short v medvědím režimu", f"pod MA200 a RSI(2) > {thr} → short do close < MA5 (max 10)",
              "odrazy v medvědím trhu se prodávají", lambda k, thr=thr: c[k] < ma200[k] and rsi2[k] > thr,
              swing(-1, lambda j: c[j] < ma5[j], 10)))
H.append(("I Delta divergence", "pokles a RTH delta > 0 → long 1 den", "absorpce: pasivní kupci",
          lambda k: c[k] < cp[k] and F.d_rth.values[k] > 0, one_day(1)))
H.append(("I Delta divergence", "pokles, delta > 0 a IBS < 0,3 → long 1 den", "absorpce + zavření u low",
          lambda k: c[k] < cp[k] and F.d_rth.values[k] > 0 and ibs[k] < 0.3, one_day(1)))
H.append(("J Stop-run overnight extrému", "pod overnight low a zpět v 10:00 → long do 16:00", "vybrané stopy, absorpce",
          lambda k: True, intraday(on_low_reclaim, side=1)))
H.append(("J Stop-run overnight extrému", "nad overnight high a zpět v 10:00 → short do 16:00", "vybrané stopy, absorpce",
          lambda k: True, intraday(on_low_reclaim, side=-1)))
for b, a in ((1, 3), (2, 3), (1, 1)):
    H.append(("K Přelom měsíce", f"close {b}. den před koncem měsíce → close {a}. dne nového měsíce", "příliv peněz (mzdy, fondy, rebalancing)",
              lambda k, b=b: tom(k, before=b), lambda k, b=b, a=a: (c[min(k + b + a, N - 1)] - c[k] - COST, min(k + b + a, N - 1), 1)))


# ------------------------------------------------------------------ 2. kolo (ROUND=2)
ROUND = os.environ.get("ROUND", "1")
if ROUND == "2":
    sys.path.insert(0, os.path.dirname(__file__)); from fomc import FOMC
    H = []
    dd = dates.values.astype("datetime64[D]")
    nxt = np.r_[dd[1:], dd[-1] + 7]
    pre_hol = np.array([np.busday_count(a, b) > 1 for a, b in zip(dd, nxt)])   # zítra (pracovní den) se neobchoduje
    wk = dates.to_period("W").values
    last_of_week = np.r_[wk[1:] != wk[:-1], True]
    fomc_k = set(np.flatnonzero(np.isin(dd, np.array(FOMC, dtype="datetime64[D]"))))
    def px_before(k, t):
        i0, i1 = int(F.i0.values[k]), int(F.i1.values[k]); ii = np.arange(i0, i1 + 1); ii = ii[BT[ii] < t]
        return BC[ii[-1]]
    # 3. pátek v měsíci (nebo poslední obchodní den před ním)
    opex = np.zeros(N, bool)
    for per in pd.PeriodIndex(dates, freq="M").unique():
        first = per.start_time; fr = pd.date_range(first, first + pd.Timedelta(days=27), freq="W-FRI")[2]
        cand = np.flatnonzero((dates <= fr) & (dates >= first))
        if len(cand): opex[cand[-1]] = True
    opex_idx = np.flatnonzero(opex)
    def next_true(arr, k):
        j = np.flatnonzero(arr[k + 1:]); return k + 1 + j[0] if len(j) else None

    for thr in (0.0, 1.0):
        H.append(("L Týdenní reverze", f"týden dolů{f' o víc než {thr:g} ATR' if thr else ''} → long pátek close do dalšího pátku",
                  "rebalancing a reverze týdenních pohybů",
                  lambda k, thr=thr: last_of_week[k] and k >= 6 and (c[k] - c[np.flatnonzero(last_of_week[:k])[-1]] < -thr * atr[k]),
                  lambda k: (lambda j: (c[j] - c[k] - COST, j, 1))(next_true(last_of_week, k) or N - 1)))
    H.append(("M Víkend a pondělí", "pátek close → pondělí close", "víkendová prémie, pondělní toky",
              lambda k: last_of_week[k] and not pre_hol[k], one_day(1)))
    H.append(("M Víkend a pondělí", "pondělí open → close", "pondělní toky",
              lambda k: k > 0 and last_of_week[k - 1], intraday(lambda k: c[k] - o[k] - COST)))
    H.append(("N Před svátkem", "close 2 dny před svátkem → close den před svátkem", "optimismus před svátkem, nízká likvidita (Ariel 1990)",
              lambda k: k + 1 < N and pre_hol[k + 1], one_day(1)))
    H.append(("N Před svátkem", "close den před svátkem → close po svátku", "totéž přes svátek",
              lambda k: pre_hol[k], one_day(1)))
    H.append(("O Před FOMC (Lucca–Moench)", "close den před FOMC → 13:58 v den FOMC", "riziková prémie před oznámením",
              lambda k: (k + 1) in fomc_k, lambda k: (px_before(k + 1, 13 * 3600 + 58 * 60) - c[k] - COST, k + 1, 0)))
    H.append(("O Před FOMC (Lucca–Moench)", "open → 13:58 v den FOMC", "totéž, jen seance",
              lambda k: k in fomc_k, intraday(lambda k: px_before(k, 13 * 3600 + 58 * 60) - o[k] - COST)))
    H.append(("O Před FOMC (Lucca–Moench)", "close den před FOMC → close v den FOMC", "včetně reakce",
              lambda k: (k + 1) in fomc_k, one_day(1)))
    H.append(("P Opční expirace", "long týden expirace (pátek close před → close expirace)", "pinning a dealer hedging (Stivers–Sun)",
              lambda k: (next_true(opex, k) is not None) and last_of_week[k] and 3 <= next_true(opex, k) - k <= 5,
              lambda k: (lambda j: (c[j] - c[k] - COST, j, 1))(next_true(opex, k))))
    H.append(("P Opční expirace", "short týden po expiraci (close expirace → další pátek)", "uvolnění hedgí po expiraci",
              lambda k: opex[k], lambda k: (lambda j: (-(c[j] - c[k]) - COST, j, -1))(next_true(last_of_week, k) or N - 1)))
    for n in (5, 10):
        H.append(("Q N-denní low nad MA200 (Connors)", f"close = {n}denní low a nad MA200 → long do close > MA5 (max 10)",
                  "nákup slabosti v býčím trendu", lambda k, n=n: c[k] <= c[k - n + 1:k + 1].min() and c[k] > ma200[k],
                  swing(1, lambda j: c[j] > ma5[j], 10)))
    H.append(("R Reverze na konci dne (a posteriori!)", "pohyb open→15:30 > 0,5 ATR → proti němu 15:30–16:00", "vyrovnávání MOC, uzavírání intradenních pozic",
              lambda k: True, intraday(lambda k: (lambda mv: None if abs(mv) < 0.5 * atr[k] else -np.sign(mv) * (F.c1600.values[k] - F.p1530.values[k]) - COST)(F.p1530.values[k] - o[k]))))
    H.append(("R Reverze na konci dne (a posteriori!)", "proti směru 1. půlhodiny, |r1| > 0,25 ATR, 15:30–16:00", "otočené Gao (v 1. kole vyšlo t −4,7)",
              lambda k: True, intraday(lambda k: (lambda r: -r - 2 * COST if r is not None else None)(intraday_mom(k, thr=0.25)))))


if ROUND == "3":
    H = []
    nbar = (F.i1.values - F.i0.values + 1).astype(float)       # počet volume barů v RTH = objem / 5000
    vol20 = pd.Series(nbar).rolling(20).mean().shift(1).values
    dr = F.d_rth.values
    mm = dates.to_period("M").values
    first_k = {per: np.flatnonzero(mm == per)[0] for per in np.unique(mm)}
    days_left = np.array([np.flatnonzero(mm == mm[k])[-1] - k for k in range(N)])
    mtd = np.array([c[k] - c[max(first_k[mm[k]] - 1, 0)] for k in range(N)])
    for side in (1, -1):
        H.append(("S Absorpce (pasivní strana vyhrává)",
                  "růst, ale delta < 0 (pasivní kupci) → long 1 den" if side > 0 else "pokles, ale delta > 0 (pasivní prodejci) → short 1 den",
                  "limitní objednávky velkých hráčů absorbují agresory",
                  lambda k, side=side: (c[k] > cp[k] and dr[k] < 0) if side > 0 else (c[k] < cp[k] and dr[k] > 0), one_day(side)))
    H.append(("S Absorpce (pasivní strana vyhrává)", "oba směry dohromady", "totéž",
              lambda k: (c[k] > cp[k] and dr[k] < 0) or (c[k] < cp[k] and dr[k] > 0),
              lambda k: one_day(1 if c[k] > cp[k] else -1)(k)))
    H.append(("S Absorpce (pasivní strana vyhrává)", "silná verze: |delta| > medián 20 dní, oba směry", "totéž",
              lambda k: k > 21 and abs(dr[k]) > np.median(np.abs(dr[k - 20:k])) and ((c[k] > cp[k] and dr[k] < 0) or (c[k] < cp[k] and dr[k] > 0)),
              lambda k: one_day(1 if c[k] > cp[k] else -1)(k)))
    for m in (1.3, 1.6):
        H.append(("T Kapitulační objem", f"pokles a objem > {m:g}× průměr 20 dní → long do close > včerejší high (max 5)",
                  "vyprodání při panice", lambda k, m=m: c[k] < cp[k] and nbar[k] > m * vol20[k],
                  swing(1, lambda j: c[j] > h[j - 1], 5)))
    for thr in (1.5, 2.5):
        H.append(("U Rebalancing na konci měsíce", f"3 dny před koncem měsíce: MTD > +{thr:g} ATR → short, < −{thr:g} ATR → long, do konce měsíce",
                  "penzijní fondy vracejí váhy akcií", lambda k, thr=thr: days_left[k] == 3 and abs(mtd[k]) > thr * atr[k],
                  lambda k: (lambda d: (d * (c[k + 3] - c[k]) - COST, k + 3, d))(-1 if mtd[k] > 0 else 1)))
    H.append(("V Býčí reverzní den", "gap dolů > 0,2 ATR a close > open → long 1 den", "neúspěšný výprodej",
              lambda k: o[k] - F.c1600.values[k - 1] < -0.2 * atr[k] and c[k] > o[k], one_day(1)))
    H.append(("V Býčí reverzní den", "nové 20denní low intradenně a close v horní polovině → long 1 den", "odmítnutí nižších cen",
              lambda k: l[k] < l[k - 20:k].min() and ibs[k] > 0.5, one_day(1)))


if ROUND == "4":
    H = []
    # Globex: první bar seance (18:00 předchozího dne) a poslední bar předchozí seance (≤ 17:00)
    sday_b = (df.index + pd.Timedelta(hours=6)).normalize()
    starts = pd.Series(np.arange(len(df)), index=sday_b).groupby(level=0).first()
    ends = pd.Series(np.arange(len(df)), index=sday_b).groupby(level=0).last()
    g_open = starts.reindex(dates).values; prev_end = ends.shift(1).reindex(dates).values
    monday = np.r_[False, dates.dayofweek.values[1:] < dates.dayofweek.values[:-1]]   # první obchodní den týdne
    def reopen_fade(k, thr=0.1, only_monday=True):
        if only_monday and not monday[k]: return None
        a, b = g_open[k], prev_end[k]
        if np.isnan(a) or np.isnan(b): return None
        a, b = int(a), int(b); ref = BC[b]; g = BO[a] - ref
        if abs(g) < max(thr * atr[k], 1.0): return None
        d = -np.sign(g); e = BO[a]
        for i in range(a, int(F.i0.values[k])):
            if (d > 0 and BH[i] >= ref) or (d < 0 and BL[i] <= ref): return d * (ref - e) - COST
        return d * (o[k] - e) - COST
    for thr, mon in ((0.1, True), (0.25, True), (0.1, False)):
        H.append(("W Fade gapu po znovuotevření Globexu", f"gap > {thr:g} ATR, {'jen neděle večer' if mon else 'každý den 18:00'} → proti gapu do zaplnění nebo 09:30",
                  "přehnaná reakce v tenkém trhu po přestávce", lambda k: True, intraday(reopen_fade, thr=thr, only_monday=mon)))
    def euro_mom(k, thr=0.0, rev=False):
        a = F.p0300.values[k] - F.c1600.values[k - 1]
        if np.isnan(a) or abs(a) < thr * atr[k] or a == 0: return None
        d = np.sign(a) * (-1 if rev else 1)
        return d * (o[k] - F.p0300.values[k]) - COST
    for thr, rev in ((0.0, False), (0.2, False), (0.2, True)):
        H.append(("X Evropská seance", f"směr 16:00→03:00 {'proti' if rev else 'po'} něm 03:00→09:30{f', |pohyb| > {thr:g} ATR' if thr else ''}",
                  "evropské informace a toky", lambda k: True, intraday(euro_mom, thr=thr, rev=rev)))


if ROUND == "5":
    H = []
    nbar = (F.i1.values - F.i0.values + 1).astype(float); vol20 = pd.Series(nbar).rolling(20).mean().shift(1).values
    dr = F.d_rth.values
    dd = dates.values.astype("datetime64[D]"); nxt = np.r_[dd[1:], dd[-1] + 7]
    pre_hol = np.array([np.busday_count(a, b) > 1 for a, b in zip(dd, nxt)])
    H.append(("1 RSI(2)", "RSI(2) < 10 nad MA200 → do close > MA5 (max 10)", "", lambda k: rsi2[k] < 10 and c[k] > ma200[k], swing(1, lambda j: c[j] > ma5[j], 10)))
    for n, ex, mh in ((3, "up", 10), (3, "ma5", 10), (3, "hi", 10), (3, "up", 5), (3, "up_ma200", 10), (2, "up", 10), (4, "up", 10), (5, "up", 10)):
        exit_fn = {"up": lambda j: c[j] > c[j - 1], "ma5": lambda j: c[j] > ma5[j], "hi": lambda j: c[j] > h[j - 1], "up_ma200": lambda j: c[j] > c[j - 1]}[ex]
        cond = (lambda k, n=n: all(c[k - i] < c[k - i - 1] for i in range(n)) and c[k] > ma200[k]) if ex == "up_ma200" else \
               (lambda k, n=n: all(c[k - i] < c[k - i - 1] for i in range(n)))
        lab = {"up": "do 1. vyššího close", "ma5": "do close > MA5", "hi": "do close > včerejší high", "up_ma200": "jen nad MA200, do 1. vyššího close"}[ex]
        H.append(("2 Série poklesů", f"{n} nižší close → {lab} (max {mh})", "", cond, swing(1, exit_fn, mh)))
    for m in (1.4, 1.6, 1.8, 2.0):
        H.append(("3 Kapitulační objem", f"pokles a objem > {m:g}× průměr 20 dní → do close > včerejší high (max 5)", "",
                  lambda k, m=m: c[k] < cp[k] and nbar[k] > m * vol20[k], swing(1, lambda j: c[j] > h[j - 1], 5)))
    H.append(("3 Kapitulační objem", "pokles a objem > 1,6× → do 1. vyššího close (max 5)", "",
              lambda k: c[k] < cp[k] and nbar[k] > 1.6 * vol20[k], swing(1, lambda j: c[j] > c[j - 1], 5)))
    for hold in (1, 2, 3):
        H.append(("4 Absorpce short", f"pokles a delta > 0 → short {hold} den/dny", "",
                  lambda k: c[k] < cp[k] and dr[k] > 0, lambda k, hold=hold: (-(c[k + hold] - c[k]) - COST, k + hold, -1)))
    H.append(("4 Absorpce short", "pokles a delta > 0, pod MA200 → short 1 den", "",
              lambda k: c[k] < cp[k] and dr[k] > 0 and c[k] < ma200[k], one_day(-1)))
    H.append(("4 Absorpce short", "pokles a delta > 0, nad MA200 → short 1 den", "",
              lambda k: c[k] < cp[k] and dr[k] > 0 and c[k] > ma200[k], one_day(-1)))
    H.append(("5 Před svátkem", "close 2 dny před svátkem → close den před svátkem", "", lambda k: k + 1 < N and pre_hol[k + 1], one_day(1)))

# ------------------------------------------------------------------ vyhodnocení
def simulate(cond, trade, days=ELIG, sequential=True):
    tr, busy = [], -1
    for k in days:
        if sequential and k <= busy: continue
        if not cond(k): continue
        r = trade(k)
        if r is None: continue
        pnl, j, d = r; tr.append((k, j, pnl, d)); busy = j if j > k else k
    return tr

def daily_pnl(tr):
    P = np.zeros(N)
    for k, j, pnl, d in tr:
        if j > k and d != 0:      # vícedenní / přes noc: přecenění po dnech
            for m, v in mtm(k, j, d): P[m] += v
            P[j] -= COST
        else:
            P[j if j > k else k] += pnl
    return P

def tstat(x):
    x = np.asarray(x, float); return x.mean() / x.std(ddof=1) * np.sqrt(len(x)) if len(x) > 2 and x.std() > 0 else np.nan

rng = np.random.default_rng(7)
rows, TR = [], {}
for fam, var, mech, cond, trade in H:
    tr = simulate(cond, trade); TR[f"{fam} | {var}"] = tr
    if len(tr) < 20: rows.append(dict(rodina=fam, varianta=var, obchodu=len(tr))); continue
    p = np.array([x[2] for x in tr]); kk = np.array([x[0] for x in tr]); yrs = dates[kk].year
    # nula: stejná pravidla v náhodné dny
    all_days = [k for k in ELIG]
    base = [trade(k) for k in all_days]
    base = np.array([b[0] for b in base if b is not None])
    null = np.array([rng.choice(base, len(p)).mean() for _ in range(2000)])
    P = daily_pnl(tr); X = np.c_[np.ones(N - WARM), mkt[WARM:]]; y = P[WARM:]
    beta, *_ = np.linalg.lstsq(X, y, rcond=None); res = y - X @ beta
    se = np.sqrt(res.var(ddof=2) * np.linalg.inv(X.T @ X)[0, 0])
    ys = pd.Series(p, index=yrs).groupby(level=0).sum()
    is_ = p[yrs < 2022]; oos = p[yrs >= 2022]
    rows.append(dict(rodina=fam, varianta=var, mechanismus=mech, obchodu=len(p), win=(p > 0).mean() * 100,
                     b_obchod=p.mean(), t=tstat(p), bez_podminky_b=base.mean(), nad_nahodou_b=p.mean() - null.mean(),
                     p_nahoda=(null >= p.mean()).mean(), alfa_b_den=beta[0], alfa_t=beta[0] / se, beta=beta[1],
                     is_b=is_.mean(), is_t=tstat(is_), oos_b=oos.mean(), oos_t=tstat(oos),
                     kladne_roky=f"{(ys > 0).sum()}/{len(ys)}", usd=p.sum() * 50))
    print(f"{fam[:30]:30s} {var[:55]:55s} n {len(p):4d} {p.mean():6.2f} t {tstat(p):5.2f} p {rows[-1]['p_nahoda']:.3f} alfa t {beta[0]/se:5.2f} IS {tstat(is_):5.2f} OOS {tstat(oos):5.2f}", flush=True)
R = pd.DataFrame(rows); R.to_csv(os.path.join(OUT, f"hypotezy_kolo{ROUND}{os.environ.get('TAG', '')}.csv"), index=False)
pd.to_pickle(TR, os.path.join(OUT, f"_trades_kolo{ROUND}{os.environ.get('TAG', '')}.pkl"))
print("hotovo,", len(R), "variant")
