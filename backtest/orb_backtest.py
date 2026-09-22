#!/usr/bin/env python3
"""
Rychlý backtest ORB RRR strategie na datech exportovaných ze Sierra Chart.

Export v Sierra Chart:  Edit >> Export Bar Data To Text File  (např. 5min ES)
Soubor má hlavičku:     Date, Time, Open, High, Low, Last, Volume, ...

Logika je 1:1 se studií sierra/ORB_RRR.cpp:
  - Opening Range = high/low od --start po dobu --or-min minut
  - vstup na ZAVŘENÍ svíčky mimo range (1 obchod denně)
  - SL = opačná strana range (nebo střed: --stop mid)
  - TP = riziko * RRR
  - exit na --flatten, pokud nezasáhne SL/TP
  - když svíčka zasáhne SL i TP zároveň, počítá se SL (konzervativně)

Příklady:
  python orb_backtest.py ES_5min.txt --rrr 1.5
  python orb_backtest.py ES_5min.txt --sweep 0.5 1 1.5 2 3 --oos 0.3
"""
import argparse
import csv
from collections import OrderedDict


def hms(s):
    h, m = s.split(":")[:2]
    return int(h) * 3600 + int(m) * 60


def load_bars(path):
    days = OrderedDict()
    with open(path, newline="") as f:
        reader = csv.reader(f)
        header = [h.strip().lower() for h in next(reader)]
        ix = {name: header.index(name) for name in ("date", "time", "open", "high", "low")}
        ix["close"] = header.index("last") if "last" in header else header.index("close")
        for row in reader:
            if not row or not row[0].strip():
                continue
            d = row[ix["date"]].strip()
            t = row[ix["time"]].strip().split(".")[0]
            hh, mm, *ss = t.split(":")
            secs = int(hh) * 3600 + int(mm) * 60 + (int(ss[0]) if ss else 0)
            bar = (secs, float(row[ix["open"]]), float(row[ix["high"]]),
                   float(row[ix["low"]]), float(row[ix["close"]]))
            days.setdefault(d, []).append(bar)
    return days


def run_day(bars, p):
    """Vrátí (body, směr, entry, exit, důvod) nebo None = žádný obchod."""
    t_start, t_or_end = p.start, p.start + p.or_min * 60
    hi = lo = None
    pos = 0
    entry = stop = target = 0.0
    for secs, o, h, l, c in bars:
        if t_start <= secs < t_or_end:
            hi = h if hi is None else max(hi, h)
            lo = l if lo is None else min(lo, l)
            continue
        if hi is None or secs < t_or_end:
            continue

        if pos != 0:
            if pos > 0:
                if l <= stop:
                    return stop - entry, pos, entry, stop, "SL"
                if h >= target:
                    return target - entry, pos, entry, target, "TP"
            else:
                if h >= stop:
                    return entry - stop, pos, entry, stop, "SL"
                if l <= target:
                    return entry - target, pos, entry, target, "TP"
            if secs >= p.flatten:
                return (c - entry) * pos, pos, entry, c, "EOD"
            continue

        if secs >= p.flatten or secs > p.last_entry:
            return None
        rng_ticks = (hi - lo) / p.tick
        if p.min_ticks and rng_ticks < p.min_ticks:
            return None
        if p.max_ticks and rng_ticks > p.max_ticks:
            return None

        sig = 0
        if p.direction != "short" and c > hi:
            sig = 1
        elif p.direction != "long" and c < lo:
            sig = -1
        if not sig:
            continue
        mid = (hi + lo) / 2
        stop = (mid if p.stop == "mid" else lo) if sig > 0 else (mid if p.stop == "mid" else hi)
        risk = (c - stop) * sig
        if risk <= 0:
            return None
        reward = round(risk * p.rrr / p.tick) * p.tick
        entry, pos = c, sig
        target = entry + reward * sig
    if pos != 0:  # data skončila před flatten časem
        return (bars[-1][4] - entry) * pos, pos, entry, bars[-1][4], "EOD"
    return None


def stats(trades, p):
    n = len(trades)
    if n == 0:
        return dict(trades=0)
    pnl = [pts * p.point_value * p.qty - p.commission * p.qty for pts in trades]
    wins = [x for x in pnl if x > 0]
    losses = [x for x in pnl if x <= 0]
    eq = peak = mdd = 0.0
    for x in pnl:
        eq += x
        peak = max(peak, eq)
        mdd = min(mdd, eq - peak)
    gross_loss = -sum(losses)
    return dict(
        trades=n,
        winrate=100 * len(wins) / n,
        net=sum(pnl),
        avg=sum(pnl) / n,
        pf=(sum(wins) / gross_loss) if gross_loss else float("inf"),
        maxdd=mdd,
    )


def fmt(name, s):
    if s["trades"] == 0:
        return f"{name:<14} no trades"
    return (f"{name:<14} trades {s['trades']:>4} | win {s['winrate']:5.1f}% | "
            f"net {s['net']:>10.2f} | avg {s['avg']:>8.2f} | PF {s['pf']:5.2f} | "
            f"maxDD {s['maxdd']:>9.2f}")


def build_parser():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file")
    ap.add_argument("--rrr", type=float, default=1.5)
    ap.add_argument("--sweep", type=float, nargs="+", help="otestuje více RRR najednou")
    ap.add_argument("--start", type=hms, default=hms("09:30"), help="začátek seance (čas v datech)")
    ap.add_argument("--or-min", type=int, default=15, help="délka opening range v minutách")
    ap.add_argument("--last-entry", type=hms, default=hms("11:30"))
    ap.add_argument("--flatten", type=hms, default=hms("15:55"))
    ap.add_argument("--stop", choices=["range", "mid"], default="range")
    ap.add_argument("--direction", choices=["both", "long", "short"], default="both")
    ap.add_argument("--min-ticks", type=int, default=0)
    ap.add_argument("--max-ticks", type=int, default=0)
    ap.add_argument("--tick", type=float, default=0.25, help="tick size (ES/MES 0.25)")
    ap.add_argument("--point-value", type=float, default=50.0, help="$ za bod (ES 50, MES 5, NQ 20)")
    ap.add_argument("--qty", type=int, default=1)
    ap.add_argument("--commission", type=float, default=4.0, help="$ round-trip na kontrakt")
    ap.add_argument("--oos", type=float, default=0.3, help="podíl dat na konci jako out-of-sample")
    ap.add_argument("--trades", help="uloží seznam obchodů do CSV (pro kontrolu vs. Sierra)")
    return ap


def main():
    p = build_parser().parse_args()

    days = load_bars(p.file)
    keys = list(days.keys())
    split = int(len(keys) * (1 - p.oos))
    print(f"Days: {len(keys)}  |  in-sample {keys[0]} .. {keys[max(split-1,0)]}"
          + (f"  |  out-of-sample {keys[split]} .. {keys[-1]}" if split < len(keys) else ""))

    for rrr in (p.sweep or [p.rrr]):
        p.rrr = rrr
        res = [(k, run_day(days[k], p)) for k in keys]
        is_tr = [r[0] for k, r in res[:split] if r]
        oos_tr = [r[0] for k, r in res[split:] if r]
        print(f"\n=== RRR 1:{rrr:g} | stop={p.stop} | dir={p.direction} ===")
        print(fmt("In-sample", stats(is_tr, p)))
        print(fmt("Out-of-sample", stats(oos_tr, p)))
        print(fmt("All", stats(is_tr + oos_tr, p)))
        if p.trades:
            out = p.trades if len(p.sweep or [0]) == 1 else p.trades.replace(".csv", f"_rrr{rrr:g}.csv")
            with open(out, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["date", "side", "entry", "exit", "reason", "points", "pnl_usd"])
                for k, r in res:
                    if r:
                        usd = r[0] * p.point_value * p.qty - p.commission * p.qty
                        w.writerow([k, "LONG" if r[1] > 0 else "SHORT", r[2], r[3], r[4],
                                    round(r[0], 2), round(usd, 2)])
            print(f"Trades saved: {out}")


if __name__ == "__main__":
    main()
