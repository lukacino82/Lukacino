"""Backtest studie PrevSessionHighBreakout.cpp (rezim Custom Time Window) na 1min datech ES.

Replikuje logiku studie bar po baru:
  - klice oken (WindowKey), fixace high/low predchozi session na prvnim baru po jejim konci,
    zahozeni neuplne prvni session
  - vstup long pri prurazu PSH zespodu v ramci obchodni session (predchozi bar teze session
    zavrel <= PSH nebo aktualni bar otevrel <= PSH)
  - SL = low predchozi session, TP = vstup + RR * riziko, flatten ve Flatten Time / konci session
  - max N obchodu za session

Model plneni:
  live  = jako realny cas: vstup na prvnim ticku nad PSH (PSH + 1 tick, pri gapu open baru)
  close = jako bar-based backtest v Sierra Chart: vstup na close baru, ktery zavrel nad PSH
Pokud bar zasahne stop i target, pocita se stop (konzervativne).

Pouziti: python backtest_psh.py ES3000.txt
"""
import sys
import numpy as np
import pandas as pd

TICK = 0.25
PV = 50.0          # USD za bod ES
COST = 25.0        # USD na round-trip (komise + skluz)


def hms(s):
    h, m = s.split(":")
    return int(h) * 3600 + int(m) * 60


def load(path):
    df = pd.read_csv(path, skipinitialspace=True)
    df.columns = [c.strip() for c in df.columns]
    dt = pd.to_datetime(df["Date"] + " " + df["Time"], format="%Y/%m/%d %H:%M:%S")
    return pd.DataFrame({"dt": dt, "o": df["Open"], "h": df["High"], "l": df["Low"], "c": df["Last"]})


def in_win(t, s, e):
    return (t >= s) & (t < e) if s < e else (t >= s) | (t < e)


def win_key(day, t, s, e):
    k = np.where(in_win(t, s, e), day, -1)
    if s > e:
        k = np.where((k != -1) & (t < e), k - 1, k)
    return k


def run(df, ref, trade, flatten, rr=1.0, max_sess=1, fill="live", close_eos=True, direction="long"):
    t = (df.dt.dt.hour * 3600 + df.dt.dt.minute * 60).to_numpy()
    day = df.dt.to_numpy().astype("datetime64[D]").astype(np.int64)
    o, h, l, c = (df[x].to_numpy() for x in "ohlc")
    rs, re_ = hms(ref[0]), hms(ref[1])
    ts, te = hms(trade[0]), hms(trade[1])
    fl = hms(flatten)
    kref = win_key(day, t, rs, re_)
    ktr = win_key(day, t, ts, te)
    infl = in_win(t, fl, te) if in_win(np.array([fl]), ts, te)[0] else np.zeros(len(t), bool)

    trades = []
    ref_hi = ref_lo = None
    b_hi, b_lo = -np.inf, np.inf
    partial = kref[0] != -1
    n_sess = 0
    pos = None  # dict
    below = above = False
    do_long, do_short = direction in ("long", "both"), direction in ("short", "both")

    for i in range(len(t)):
        # --- novy bar: zpracovani uzavreneho baru i-1 a prechodu ---
        if i > 0:
            p = i - 1
            if kref[p] != -1:
                b_hi = max(b_hi, h[p]); b_lo = min(b_lo, l[p])
            if kref[p] != -1 and kref[i] != kref[p]:
                if partial:
                    partial = False
                else:
                    ref_hi, ref_lo = b_hi, b_lo
                    below = above = False
        if kref[i] != -1 and (i == 0 or kref[i] != kref[i - 1]):
            b_hi, b_lo = -np.inf, np.inf
        if ktr[i] != -1 and (i == 0 or ktr[i] != ktr[i - 1]):
            n_sess = 0
        if i == 0 or ktr[i] != ktr[i - 1]:
            below = above = False
        elif ktr[i] != -1 and ref_hi is not None and pos is None:
            if c[i - 1] <= ref_hi: below = True
            if c[i - 1] >= ref_lo: above = True

        # --- sprava otevrene pozice ---
        if pos is not None:
            ex = None
            if close_eos and (ktr[i] == -1 or ktr[i] != pos["key"] or infl[i]):
                ex, why = o[i], "cas"
            else:
                sd = pos["side"]
                if (o[i] - pos["sl"]) * sd <= 0:
                    ex, why = o[i], "SL"
                elif (o[i] - pos["tp"]) * sd >= 0:
                    ex, why = o[i], "TP"
                elif (l[i] if sd == 1 else h[i]) * sd <= pos["sl"] * sd:
                    ex, why = pos["sl"], "SL"
                elif (h[i] if sd == 1 else l[i]) * sd >= pos["tp"] * sd:
                    ex, why = pos["tp"], "TP"
            if ex is None:
                continue
            pos.update(exit=ex, why=why, xdt=df.dt.iat[i])
            trades.append(pos); pos = None
            if why == "cas":
                pass  # po flattenu muze ve stejnem baru nasledovat novy vstup jen pokud limit dovoli
            continue  # AllowOnlyOneTradePerBar

        # --- vstup ---
        if ref_hi is None or ktr[i] == -1 or infl[i] or n_sess >= max_sess:
            continue
        side = 0
        if do_long and (below or o[i] <= ref_hi) and (h[i] > ref_hi if fill == "live" else c[i] > ref_hi):
            side = 1
        elif do_short and (above or o[i] >= ref_lo) and (l[i] < ref_lo if fill == "live" else c[i] < ref_lo):
            side = -1
        if side == 0:
            continue
        if fill == "live":
            if side == 1:
                entry = o[i] if o[i] > ref_hi else ref_hi + TICK
            else:
                entry = o[i] if o[i] < ref_lo else ref_lo - TICK
        else:
            entry = c[i]
        sl = ref_lo if side == 1 else ref_hi
        risk = (entry - sl) * side
        if risk <= 0:
            continue
        tp = entry + side * rr * risk
        n_sess += 1
        below = above = False
        pos = dict(edt=df.dt.iat[i], side=side, entry=entry, sl=sl, tp=tp, risk=risk, key=ktr[i])
        if fill == "live":  # zbytek vstupniho baru (konzervativne: stop pred targetem)
            hit_sl = l[i] <= sl if side == 1 else h[i] >= sl
            hit_tp = h[i] >= tp if side == 1 else l[i] <= tp
            if hit_sl:
                pos.update(exit=sl, why="SL", xdt=df.dt.iat[i]); trades.append(pos); pos = None
            elif hit_tp:
                pos.update(exit=tp, why="TP", xdt=df.dt.iat[i]); trades.append(pos); pos = None

    tr = pd.DataFrame(trades)
    if tr.empty:
        return tr
    tr["pts"] = (tr.exit - tr.entry) * tr.side
    tr["gross"] = tr.pts * PV
    tr["net"] = tr.gross - COST
    tr["R"] = tr.pts / tr.risk
    return tr


def stats(tr):
    n = len(tr)
    net = tr.net
    eq = net.cumsum()
    dd = (eq - eq.cummax()).min()
    wins = net[net > 0]; losses = net[net <= 0]
    pf = wins.sum() / -losses.sum() if len(losses) and losses.sum() < 0 else np.inf
    tstat = net.mean() / net.std(ddof=1) * np.sqrt(n) if n > 1 else np.nan
    return dict(
        obchodu=n,
        win_pct=round(100 * (net > 0).mean(), 1),
        net_usd=round(net.sum()),
        gross_usd=round(tr.gross.sum()),
        na_obchod=round(net.mean(), 1),
        t=round(tstat, 2),
        PF=round(pf, 2),
        maxDD=round(dd),
        riziko_b=round(tr.risk.median(), 1),
        TP_pct=round(100 * (tr.why == "TP").mean()),
        SL_pct=round(100 * (tr.why == "SL").mean()),
        cas_pct=round(100 * (tr.why == "cas").mean()),
    )


CONFIGS = {
    "A overnight->RTH 9:30-11:30": dict(ref=("18:00", "09:30"), trade=("09:30", "11:30"), flatten="11:25"),
    "A2 overnight->RTH cely den": dict(ref=("18:00", "09:30"), trade=("09:30", "16:00"), flatten="15:55"),
    "B prvnich 30 min 10:00-12:00": dict(ref=("09:30", "10:00"), trade=("10:00", "12:00"), flatten="11:55"),
    "C predchozi RTH den": dict(ref=("09:30", "16:00"), trade=("09:30", "16:00"), flatten="15:55"),
    "D Daily (session grafu 18:00-17:00)": dict(ref=("18:00", "17:00"), trade=("18:00", "17:00"), flatten="15:55"),
}

if __name__ == "__main__":
    df = load(sys.argv[1])
    rows, by_year = [], {}
    for name, cfg in CONFIGS.items():
        for rr in (1.0, 1.5):
            for fill in ("live", "close"):
                tr = run(df, rr=rr, fill=fill, **cfg)
                s = stats(tr)
                rows.append(dict(setup=name, RR=rr, fill=fill, **s))
                if fill == "live":
                    by_year[f"{name} RR{rr}"] = tr.groupby(tr.edt.dt.year).net.sum().round()
                    tr.to_csv(f"trades_{name.split()[0]}_RR{rr}.csv", index=False)
    res = pd.DataFrame(rows)
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
    print(res.to_string(index=False))
    print()
    print(pd.DataFrame(by_year).fillna(0).astype(int).to_string())
