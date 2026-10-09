"""Hypothesis generators. Every family produces many conditions; each condition x horizon is
one test in the factory. Direction is never assumed (it is set in the discovery period)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from data import RTH0, RTH1
from factory import Factory

TICK = 0.25


def shift(a, k, fill=np.nan):
    out = np.full(a.shape, fill, dtype=float)
    if k > 0:
        out[k:] = a[:-k]
    else:
        out[:k] = a[-k:]
    return out


def day_to_bar(D, s: pd.Series):
    """series indexed by trading day (subset of D.days) -> per-bar array."""
    full = s.reindex(D.days).to_numpy(dtype=float)
    return full[D.di]


class Ctx:
    """Shared derived arrays."""

    def __init__(self, D):
        self.D = D
        T = D.T
        n = len(D.o)
        self.n = n
        c, o, v, dl = D.c, D.o, D.v, D.dl
        self.ret = (c / o - 1) * 1e4
        # volume ratio vs the same 5-min slot over the previous 20 days
        key = D.gmin
        s = pd.DataFrame({"k": key, "v": v, "r": np.abs(self.ret)})
        g = s.groupby("k")
        self.vbase = g.v.transform(lambda x: x.rolling(20, min_periods=10).mean().shift()).to_numpy()
        self.rbase = g.r.transform(lambda x: x.rolling(20, min_periods=10).mean().shift()).to_numpy()
        with np.errstate(invalid="ignore", divide="ignore"):
            self.vratio = v / self.vbase
            self.imb = np.where(v > 0, dl / v, 0.0)
        self.flow = D.flow_ok
        self.bull = day_to_bar(D, T.bull.astype(float)) > 0.5
        self.bear = day_to_bar(D, (~T.bull).astype(float)) > 0.5
        self.wd = day_to_bar(D, T.wd.astype(float))
        self.rth = D.rth
        self.first_bar_of_day = np.r_[True, D.di[1:] != D.di[:-1]]
        # levels per bar
        T2 = T.copy()
        T2["pdh"] = T2.H.shift(); T2["pdl"] = T2.L.shift(); T2["pdc"] = T2.C.shift()
        wk = T2.index.to_period("W-FRI")
        wh = T2.groupby(wk).H.max(); wl = T2.groupby(wk).L.min()
        T2["pwh"] = wh.shift().reindex(wk).to_numpy(); T2["pwl"] = wl.shift().reindex(wk).to_numpy()
        self.lv = {k: day_to_bar(D, T2[k]) for k in ("pdh", "pdl", "pdc", "pwh", "pwl")}
        onh = day_to_bar(D, T2.onH); onl = day_to_bar(D, T2.onL)
        self.lv["onh"] = np.where(self.rth, onh, np.nan)
        self.lv["onl"] = np.where(self.rth, onl, np.nan)
        pc = shift(c, 1)
        self.lv["r100"] = np.round(pc / 100) * 100
        self.lv["r50"] = np.round(pc / 50) * 50
        self.atr_bar = day_to_bar(D, T.atr)


def calendar(F: Factory, C: Ctx):
    T = F.D.T
    bull = T.bull.to_numpy()
    last_month = (T.index.year * 12 + T.index.month) == (T.index[-1].year * 12 + T.index[-1].month)
    H4 = ("cc", "oc", "on", "c5")
    for w, nm in enumerate(["Po", "Út", "St", "Čt", "Pá"]):
        m = (T.wd == w).to_numpy()
        F.day(f"Den v týdnu: {nm}", "Kalendář", m, H4, known="before")
        F.day(f"Den v týdnu: {nm} · bull", "Kalendář", m & bull, H4[:3], known="before")
        F.day(f"Den v týdnu: {nm} · bear", "Kalendář", m & ~bull, H4[:3], known="before")
    for par, nm in ((0, "sudý"), (1, "lichý")):
        F.day(f"Kalendářní den {nm}", "Kalendář", (T.dom % 2 == par).to_numpy(), H4, known="before")
        F.day(f"Obchodní den v měsíci {nm}", "Kalendář", (T.tdm % 2 == par).to_numpy(), H4, known="before")
    for d in range(1, 32):
        F.day(f"Den v měsíci {d}.", "Kalendář", (T.dom == d).to_numpy(), ("cc", "oc"), known="before")
    for d in range(1, 24):
        F.day(f"{d}. obchodní den měsíce", "Kalendář", (T.tdm == d).to_numpy(), ("cc", "oc", "on"), known="before")
    for d in range(1, 11):
        F.day(f"{d}. obchodní den od konce měsíce", "Kalendář", ((T.tdm_rev == d) & ~last_month).to_numpy(),
              ("cc", "oc", "on"), known="before")
    for mth in range(1, 13):
        F.day(f"Měsíc {mth}", "Kalendář", (T.month == mth).to_numpy(), ("cc", "oc", "on"), known="before")
        for w, nm in enumerate(["Po", "Út", "St", "Čt", "Pá"]):
            F.day(f"Měsíc {mth} · {nm}", "Kalendář", ((T.month == mth) & (T.wd == w)).to_numpy(), ("cc",), known="before")
    wom = ((T.dom - 1) // 7 + 1).to_numpy()
    for k in range(1, 6):
        F.day(f"{k}. týden měsíce", "Kalendář", wom == k, ("cc", "oc"), known="before")
        for w, nm in enumerate(["Po", "Út", "St", "Čt", "Pá"]):
            F.day(f"{k}. týden měsíce · {nm}", "Kalendář", (wom == k) & (T.wd == w).to_numpy(), ("cc", "oc"), known="before")
    ev = {"OPEX pátek": T.opex, "OPEX týden": T.opex_week, "Quad witching": T.quad,
          "Den po OPEX": T.opex.shift().fillna(False), "Týden po OPEX": T.opex_week.shift(5).fillna(False) & ~T.opex_week,
          "Den před svátkem": T.pre_hol, "Den po svátku": T.post_hol,
          "Turn of month (−1 až +3)": ((T.tdm_rev == 1) & ~last_month) | (T.tdm <= 3),
          "FOMC den (2016+)": T.fomc, "Den před FOMC (2016+)": T.fomc.shift(-1).fillna(False)}
    for k, m in ev.items():
        F.day(k, "Kalendář", np.asarray(m, bool), H4, known="before")
    moon = T.moon.to_numpy()
    for b in range(8):
        lo, hi = b * 29.53 / 8, (b + 1) * 29.53 / 8
        F.day(f"Fáze Měsíce {b + 1}/8", "Kalendář", (moon >= lo) & (moon < hi), ("cc", "oc", "c5"), known="before")
    F.day("Úplněk ±3 dny", "Kalendář", np.abs(moon - 14.77) <= 3, ("cc", "c5"), known="before")
    F.day("Nov ±3 dny", "Kalendář", (moon <= 3) | (moon >= 26.53), ("cc", "c5"), known="before")


def time_windows(F: Factory, C: Ctx):
    D = F.D
    names = ["Po", "Út", "St", "Čt", "Pá"]
    for b in range(0, 23 * 60, 30):
        hh = (18 * 60 + b) // 60 % 24
        mm = (18 * 60 + b) % 60
        lab = f"{hh:02d}:{mm:02d}"
        at = D.gmin == b
        F.bar(f"Okno {lab} ET", "Čas dne", at, ("30m", "2h"))
        for w in range(5):
            F.bar(f"Okno {lab} ET · {names[w]}", "Čas dne", at & (C.wd == w), ("30m", "2h"))


def vwap_retests(F: Factory, C: Ctx):
    D = F.D
    c, h, l = D.c, D.h, D.l
    anchors = {"RTH VWAP": (D.vw_r, C.rth), "Globex VWAP": (D.vw_g, np.ones(C.n, bool)),
               "Týdenní VWAP": (D.vw_w, np.ones(C.n, bool)), "Měsíční VWAP": (D.vw_m, np.ones(C.n, bool))}
    for an, (vw, valid) in anchors.items():
        pvw = shift(vw, 1)
        ph, pl = shift(h, 1), shift(l, 1)
        slope = vw - shift(vw, 12)
        with np.errstate(invalid="ignore"):
            above_prev = pl > pvw
            below_prev = ph < pvw
            ev = {
                "retest shora, odraz (close nad)": above_prev & (l <= vw) & (c > vw),
                "retest shora, průraz (close pod)": above_prev & (l <= vw) & (c < vw),
                "retest zdola, odraz (close pod)": below_prev & (h >= vw) & (c < vw),
                "retest zdola, průraz (close nad)": below_prev & (h >= vw) & (c > vw),
            }
        for en, m in ev.items():
            m = m & valid & np.isfinite(vw)
            same_day_first = _first_in_day(m, D.di)
            for filt, fm in (("", np.ones(C.n, bool)), (" · bull", C.bull), (" · bear", C.bear),
                             (" · VWAP roste", slope > 0), (" · VWAP klesá", slope < 0)):
                F.bar(f"{an}: {en}{filt}", "VWAP retest", m & fm, ("30m", "2h", "eod"))
                F.bar(f"{an}: {en}{filt} · první za den", "VWAP retest", same_day_first & fm, ("30m", "2h", "eod"))
        sd = {"RTH VWAP": D.sd_r, "Globex VWAP": D.sd_g, "Týdenní VWAP": D.sd_w, "Měsíční VWAP": D.sd_m}[an]
        for k in (1.0, 2.0, 3.0):
            with np.errstate(invalid="ignore"):
                up = (c > vw + k * sd) & (shift(c, 1) <= pvw + k * shift(sd, 1))
                dn = (c < vw - k * sd) & (shift(c, 1) >= pvw - k * shift(sd, 1))
            F.bar(f"{an}: close nad +{k:.0f}σ", "VWAP pásma", up & valid, ("30m", "2h", "eod", "next"))
            F.bar(f"{an}: close pod −{k:.0f}σ", "VWAP pásma", dn & valid, ("30m", "2h", "eod", "next"))


def _first_in_day(m, di):
    idx = np.flatnonzero(m)
    out = np.zeros(len(m), bool)
    if len(idx):
        _, f = np.unique(di[idx], return_index=True)
        out[idx[f]] = True
    return out


def volume_absorption(F: Factory, C: Ctx):
    """Volume shock x delta side x price response. 'Absorbed' = big volume and one-sided delta,
    but the bar barely moves: the user's hidden accumulation / distribution idea."""
    D = F.D
    for W in (1, 6, 12):  # 5 min, 30 min, 1 h windows
        if W == 1:
            vr, imb, ret, rb = C.vratio, C.imb, C.ret, C.rbase
        else:
            v = pd.Series(D.v).rolling(W).sum().to_numpy()
            vb = pd.Series(C.vbase).rolling(W).sum().to_numpy()
            dl = pd.Series(D.dl).rolling(W).sum().to_numpy()
            vr = v / vb
            imb = np.where(v > 0, dl / v, 0)
            ret = (D.c / shift(D.o, W - 1) - 1) * 1e4
            rb = pd.Series(C.rbase).rolling(W).sum().to_numpy() / np.sqrt(W)
        lab = {1: "5 min", 6: "30 min", 12: "1 h"}[W]
        with np.errstate(invalid="ignore"):
            for vk in (2.0, 3.0, 5.0):
                big = (vr >= vk) & C.flow
                for side, sm in (("nákupní delta", imb >= 0.10), ("prodejní delta", imb <= -0.10)):
                    s = 1 if side.startswith("nák") else -1
                    resp = {"cena stojí (absorpce)": np.abs(ret) < 0.5 * rb,
                            "cena jde s deltou": (s * ret) > 1.0 * rb,
                            "cena jde proti deltě": (s * ret) < -0.5 * rb}
                    for rn, rm in resp.items():
                        m = big & sm & rm
                        for filt, fm in (("", np.ones(C.n, bool)), (" · RTH", C.rth), (" · mimo RTH", ~C.rth)):
                            F.bar(f"Objem ≥{vk:.0f}× ({lab}), {side}, {rn}{filt}", "Objem a absorpce",
                                  m & fm, ("30m", "2h", "eod", "next"))
    # daily scale
    T = D.T
    vol20 = T.gvol.rolling(20).mean().shift()
    vr = T.gvol / vol20
    imb = T.gdelta / T.gvol
    zi = (imb - imb.rolling(60).mean().shift()) / imb.rolling(60).std().shift()
    ret_atr = (T.C - T.pC) / T.atr
    ok = (T.index >= "2010-06-01")
    for vk in (1.3, 1.6, 2.0):
        for side, sm in (("nákupní", zi >= 1.0), ("prodejní", zi <= -1.0)):
            s = 1 if side == "nákupní" else -1
            for rn, rm in (("cena stojí", ret_atr.abs() < 0.3), ("cena s deltou", s * ret_atr > 0.5),
                           ("cena proti deltě", s * ret_atr < -0.3)):
                m = (vr >= vk) & sm & rm & ok
                F.day(f"Denní objem ≥{vk}×, {side} delta (z≥1), {rn}", "Objem a absorpce", m.to_numpy(), ("cc", "oc", "c5", "c20"))


def cvd_divergence(F: Factory, C: Ctx):
    D = F.D
    ok = C.flow
    cvd = D.cvd
    for W, lab in ((12, "1 h"), (24, "2 h"), (48, "4 h"), (78, "6,5 h"), (276, "1 den"), (1380, "5 dní")):
        dp = D.c - shift(D.c, W)
        dc = cvd - shift(cvd, W)
        vv = pd.Series(D.v).rolling(W).sum().to_numpy()
        nc = dc / vv  # signed imbalance over the window
        sp = pd.Series(np.abs(dp)).rolling(5000, min_periods=500).median().shift().to_numpy()
        hi = pd.Series(D.h).rolling(W).max().to_numpy()
        lo = pd.Series(D.l).rolling(W).min().to_numpy()
        chi = pd.Series(cvd).rolling(W).max().to_numpy()
        clo = pd.Series(cvd).rolling(W).min().to_numpy()
        with np.errstate(invalid="ignore"):
            for mag in (1.0, 2.0):
                bullish = (dp < -mag * sp) & (nc > 0.02) & ok
                bearish = (dp > mag * sp) & (nc < -0.02) & ok
                F.bar(f"CVD divergence {lab}: cena dolů ≥{mag:.0f}× med., delta plus", "CVD divergence", bullish, ("30m", "2h", "eod", "next"))
                F.bar(f"CVD divergence {lab}: cena nahoru ≥{mag:.0f}× med., delta mínus", "CVD divergence", bearish, ("30m", "2h", "eod", "next"))
            nh = (D.h >= hi) & (cvd < chi - 0.25 * (chi - clo)) & ok
            nl = (D.l <= lo) & (cvd > clo + 0.25 * (chi - clo)) & ok
            F.bar(f"Nové {lab} high bez nového high CVD", "CVD divergence", nh, ("30m", "2h", "eod", "next"))
            F.bar(f"Nové {lab} low bez nového low CVD", "CVD divergence", nl, ("30m", "2h", "eod", "next"))
    # days / weeks / months on daily data
    T = D.T
    dd = T.gdelta.where(T.index >= "2010-06-01")
    vol = T.gvol
    for N, lab in ((3, "3 dny"), (5, "1 týden"), (10, "2 týdny"), (20, "1 měsíc"), (60, "3 měsíce"),
                   (130, "6 měsíců"), (260, "1 rok")):
        pr = T.C / T.C.shift(N) - 1
        imb = dd.rolling(N).sum() / vol.rolling(N).sum()
        zi = (imb - imb.rolling(250, min_periods=100).mean()) / imb.rolling(250, min_periods=100).std()
        zp = pr / (T.ret.rolling(250, min_periods=100).std() * np.sqrt(N))
        for th in (0.5, 1.0, 1.5):
            F.day(f"CVD divergence {lab}: cena dolů (z≤−{th}), delta nahoru (z≥{th})", "CVD divergence",
                  ((zp <= -th) & (zi >= th)).to_numpy(), ("cc", "c5", "c20"))
            F.day(f"CVD divergence {lab}: cena nahoru (z≥{th}), delta dolů (z≤−{th})", "CVD divergence",
                  ((zp >= th) & (zi <= -th)).to_numpy(), ("cc", "c5", "c20"))
            F.day(f"CVD souhlas {lab}: cena i delta nahoru (z≥{th})", "CVD divergence",
                  ((zp >= th) & (zi >= th)).to_numpy(), ("cc", "c5", "c20"))
            F.day(f"CVD souhlas {lab}: cena i delta dolů (z≤−{th})", "CVD divergence",
                  ((zp <= -th) & (zi <= -th)).to_numpy(), ("cc", "c5", "c20"))
        hiN = T.H.rolling(N).max(); loN = T.L.rolling(N).min()
        cv = dd.cumsum()
        F.day(f"Nové {lab} high, CVD pod svým {lab} maximem", "CVD divergence",
              ((T.H >= hiN) & (cv < cv.rolling(N).max() - 0.2 * (cv.rolling(N).max() - cv.rolling(N).min()))).to_numpy(), ("cc", "c5", "c20"))
        F.day(f"Nové {lab} low, CVD nad svým {lab} minimem", "CVD divergence",
              ((T.L <= loN) & (cv > cv.rolling(N).min() + 0.2 * (cv.rolling(N).max() - cv.rolling(N).min()))).to_numpy(), ("cc", "c5", "c20"))


def sweeps(F: Factory, C: Ctx):
    """Stop hunts: trade beyond a known level and close back inside (reject) or beyond (accept)."""
    D = F.D
    names = {"pdh": "high předchozího dne", "pdl": "low předchozího dne", "onh": "overnight high",
             "onl": "overnight low", "pwh": "high minulého týdne", "pwl": "low minulého týdne",
             "pdc": "close předchozího dne", "r100": "kulaté číslo 100", "r50": "kulaté číslo 50"}
    for k, L in C.lv.items():
        for p in (1, 4, 8, 16):
            pen = p * TICK
            with np.errstate(invalid="ignore"):
                prev_below = shift(D.c, 1) < L
                prev_above = shift(D.c, 1) > L
                up_rej = prev_below & (D.h >= L + pen) & (D.c < L)
                up_acc = prev_below & (D.c >= L + pen)
                dn_rej = prev_above & (D.l <= L - pen) & (D.c > L)
                dn_acc = prev_above & (D.c <= L - pen)
            for nm, m in ((f"sweep nad {names[k]} o ≥{p} ticků a návrat pod", up_rej),
                          (f"close nad {names[k]} o ≥{p} ticků (přijetí)", up_acc),
                          (f"sweep pod {names[k]} o ≥{p} ticků a návrat nad", dn_rej),
                          (f"close pod {names[k]} o ≥{p} ticků (přijetí)", dn_acc)):
                m1 = _first_in_day(m & np.isfinite(L), D.di)
                F.bar(f"Stop-hunt: {nm}", "Stop-hunt / sweep", m1, ("30m", "2h", "eod"))
                F.bar(f"Stop-hunt: {nm} · RTH", "Stop-hunt / sweep", _first_in_day(m & C.rth & np.isfinite(L), D.di), ("30m", "2h", "eod"))


def crowd_patterns(F: Factory, C: Ctx):
    T = F.D.T
    up = (T.ret > 0).to_numpy()
    for k in range(1, 6):
        codes = np.zeros(len(T), int)
        valid = np.ones(len(T), bool)
        for j in range(k):
            s = np.r_[[False] * j, up[:len(up) - j]]
            codes = codes * 2 + s.astype(int)
        valid[:k] = False
        for code in range(2 ** k):
            pat = "".join("U" if (code >> (k - 1 - j)) & 1 else "D" for j in range(k))
            F.day(f"Sekvence dní {pat} (poslední vpravo)", "Vzorce davu", valid & (codes == code), ("oc", "cc", "c5"))
    atr = T.atr
    gap = (T.O - T.pC) / atr
    for lo, hi in ((-9, -1), (-1, -0.5), (-0.5, -0.2), (-0.2, 0.2), (0.2, 0.5), (0.5, 1), (1, 9)):
        m = ((gap > lo) & (gap <= hi)).to_numpy()
        F.day(f"Gap {lo}…{hi} ATR → open-close", "Vzorce davu", m, ("oc",), known="before")
        F.day(f"Gap {lo}…{hi} ATR → open-close · bull", "Vzorce davu", m & T.bull.to_numpy(), ("oc",), known="before")
    loc = (T.O - T.onL) / (T.onH - T.onL)
    for lo, hi, nm in ((-9, 0, "pod ON low"), (0, 1 / 3, "spodní třetina ON"), (1 / 3, 2 / 3, "střed ON"),
                       (2 / 3, 1, "horní třetina ON"), (1, 9, "nad ON high")):
        F.day(f"Open {nm} → open-close", "Vzorce davu", ((loc >= lo) & (loc < hi)).to_numpy(), ("oc",), known="before")
    pos = np.where(T.O > T.H.shift(), "nad PDH", np.where(T.O < T.L.shift(), "pod PDL", "uvnitř"))
    for nm in ("nad PDH", "pod PDL", "uvnitř"):
        F.day(f"Open {nm} předchozího dne → open-close", "Vzorce davu", pos == nm, ("oc",), known="before")
    ibs = ((T.C - T.L) / (T.H - T.L)).to_numpy()
    for lo, hi in ((0, .2), (.2, .4), (.4, .6), (.6, .8), (.8, 1.01)):
        m = (ibs >= lo) & (ibs < hi)
        F.day(f"IBS {lo:.1f}–{hi:.1f}", "Vzorce davu", m, ("cc", "oc", "c5"))
        F.day(f"IBS {lo:.1f}–{hi:.1f} · bull", "Vzorce davu", m & T.bull.to_numpy(), ("cc", "oc", "c5"))
    rng = (T.H - T.L)
    nr7 = (rng <= rng.rolling(7).min()).to_numpy()
    inside = ((T.H < T.H.shift()) & (T.L > T.L.shift())).to_numpy()
    outside = ((T.H > T.H.shift()) & (T.L < T.L.shift())).to_numpy()
    for nm, m in (("NR7", nr7), ("Inside day", inside), ("Outside day", outside),
                  ("Outside day, close v horní čtvrtině", outside & (ibs > .75)),
                  ("Outside day, close v dolní čtvrtině", outside & (ibs < .25))):
        F.day(nm, "Vzorce davu", m, ("cc", "oc", "c5"))
    for N in (20, 55, 100, 252):
        F.day(f"Close na {N}denním maximu", "Vzorce davu", (T.C >= T.C.rolling(N).max()).to_numpy(), ("cc", "c5", "c20"))
        F.day(f"Close na {N}denním minimu", "Vzorce davu", (T.C <= T.C.rolling(N).min()).to_numpy(), ("cc", "c5", "c20"))
    dd = T.C / T.C.cummax() - 1
    for lo, hi in ((-0.02, 0.01), (-0.05, -0.02), (-0.10, -0.05), (-0.20, -0.10), (-1, -0.20)):
        F.day(f"Drawdown od ATH {lo * 100:.0f}…{hi * 100:.0f} %", "Vzorce davu", ((dd > lo) & (dd <= hi)).to_numpy(), ("c5", "c20"))
    rsi2 = _rsi(T.C, 2)
    for th in (5, 10, 20):
        F.day(f"RSI(2) < {th}", "Vzorce davu", (rsi2 < th).to_numpy(), ("cc", "c5"))
        F.day(f"RSI(2) < {th} · bull", "Vzorce davu", ((rsi2 < th) & T.bull).to_numpy(), ("cc", "c5"))
        F.day(f"RSI(2) > {100 - th}", "Vzorce davu", (rsi2 > 100 - th).to_numpy(), ("cc", "c5"))


def _rsi(c, n):
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)


def opening_drive(F: Factory, C: Ctx):
    D = F.D
    T = D.T
    at10 = D.gmin == RTH0 + 25  # bar 09:55-10:00, close = 10:00
    o_rth = day_to_bar(D, T.O)
    r30 = (D.c - o_rth) / C.atr_bar
    for lo, hi in ((-9, -0.5), (-0.5, -0.2), (-0.2, 0), (0, 0.2), (0.2, 0.5), (0.5, 9)):
        m = at10 & (r30 > lo) & (r30 <= hi)
        F.bar(f"Prvních 30 min RTH {lo}…{hi} ATR → zbytek dne", "Opening drive", m, ("2h", "eod"))
        F.bar(f"Prvních 30 min RTH {lo}…{hi} ATR → zbytek dne · bull", "Opening drive", m & C.bull, ("2h", "eod"))


FAMILIES = [calendar, time_windows, vwap_retests, volume_absorption, cvd_divergence, sweeps, crowd_patterns, opening_drive]
