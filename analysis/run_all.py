"""Kompletní analýza hrany na jednom instrumentu (primárně ES futures).

Použití:
  python analysis/run_all.py DATA.txt --data-tz America/New_York --bar-time close \
      --cost 0.5 --out reports/es

Kroky:
  1. kontrola dat, převzorkování na --bar (default 5min)
  2. profil volatility podle času (kde je trh nejživější)
  3. mřížka parametrů pro všechny strategie (počet pokusů jde do DSR)
  4. plná validace nejlepší varianty každé strategie
  5. walk-forward (OOS) pro každou strategii
  6. podmíněné analýzy: kde hrana je a kam by se dala posunout
Výsledek: REPORT.md + CSV tabulky do --out.
"""
from __future__ import annotations

import argparse
import sys
import time as _time
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from session_edge import stats  # noqa: E402
from session_edge.config import BacktestConfig, RiskConfig  # noqa: E402
from session_edge.data import load_csv, resample  # noqa: E402
from session_edge.engine import prepare, simulate  # noqa: E402
from session_edge.profile import volatility_profile, weekday_profile  # noqa: E402
from session_edge.strategies import make_strategy  # noqa: E402
from session_edge.validation import param_grid, validate, verdict, walk_forward  # noqa: E402

ET = "America/New_York"

# strategie -> (předvolba, data jen RTH?, výstup, mřížka parametrů strategie)
STRATS = {
    "ORB 30m": ("us_orb30", True, "15:55", {"max_range_atr": [10.0, 0.35]}),
    "ORB 5m": ("us_orb5", True, "15:55", {"max_range_atr": [10.0, 0.15]}),
    "ORB 15m": ("us_orb30", True, "15:55", {"range_end": ["09:45"], "entry_end": ["11:30"],
                                             "max_range_atr": [10.0, 0.25]}),
    "ORB fade (sweep)": ("us_orb_fade", True, "15:55", {"min_excursion_atr": [0.05, 0.1]}),
    "Intraday momentum": ("us_intraday_momentum", True, "15:59", {"min_move_atr": [0.0, 0.2]}),
    "Gap fade": ("us_gap_fade", True, "15:55", {"min_gap_atr": [0.2, 0.4]}),
    "Europe open breakout": ("london_asia_breakout", False, "11:25",
                             {"range_start": ["00:00"], "range_end": ["07:00", "08:00"],
                              "entry_end": ["10:00"]}),
}

RISK_GRID = {
    "risk.rrr": [1.0, 1.5, 2.0, 3.0],
    "risk.max_trades_per_day": [1, 2],
}
MOMENTUM_RISK_GRID = {  # momentum drží do close, TP jen volitelně
    "risk.target_mode": ["none", "rrr"],
    "risk.rrr": [2.0],
}


def rth(df: pd.DataFrame) -> pd.DataFrame:
    loc = df.tz_convert(ET)
    t = loc.index.time
    m = (t >= pd.Timestamp("09:30").time()) & (t < pd.Timestamp("16:00").time())
    return df[m]


def fmt(x, nd=3):
    if isinstance(x, (float, np.floating)) and np.isfinite(x) and float(x).is_integer() and abs(x) >= 2:
        return str(int(x))
    if isinstance(x, (float, np.floating)):
        return f"{x:.{nd}f}" if np.isfinite(x) else str(x)
    return str(x)


def md_table(df: pd.DataFrame, nd=3) -> str:
    cols = [str(c) for c in df.columns]
    lines = ["| " + " | ".join([df.index.name or ""] + cols) + " |",
             "|" + "---|" * (len(cols) + 1)]
    for idx, row in df.iterrows():
        lines.append("| " + " | ".join([str(idx)] + [fmt(v, nd) for v in row.values]) + " |")
    return "\n".join(lines)


def grid_search(data, strat_name, overrides_grid, risk_grid, base_cfg):
    rows = []
    s_grid = param_grid(**overrides_grid) if overrides_grid else [{}]
    r_grid = param_grid(**risk_grid)
    for s_over in s_grid:
        strat = make_strategy(strat_name, **s_over)
        prepared = prepare(data, strat, base_cfg)
        for r_over in r_grid:
            rc = replace(base_cfg.risk, **{k[5:]: v for k, v in r_over.items()})
            cfg = replace(base_cfg, risk=rc)
            t = simulate(prepared, cfg)
            s = stats.summary(t) if len(t) else {"trades": 0}
            rows.append({**s_over, **r_over, **{k: s.get(k, np.nan) for k in
                         ("trades", "win_rate", "expectancy_r", "t_stat", "profit_factor",
                          "total_r", "max_drawdown_r", "sharpe_annual")}})
    return pd.DataFrame(rows)


def conditional(trades: pd.DataFrame, key: pd.Series, name: str, q: int | None = None) -> pd.DataFrame:
    k = pd.qcut(key, q, duplicates="drop") if q else key
    g = trades.groupby(k, observed=True)["r"]
    out = pd.DataFrame({"trades": g.size(), "win_rate": g.apply(lambda s: (s > 0).mean()),
                        "expectancy_r": g.mean(),
                        "t_stat": g.apply(lambda s: s.mean() / s.std(ddof=1) * np.sqrt(len(s))
                                          if len(s) > 2 and s.std(ddof=1) > 0 else np.nan)})
    out.index.name = name
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--data-tz", default=ET)
    ap.add_argument("--bar-time", default="open", choices=["open", "close"])
    ap.add_argument("--bar", default="5min")
    ap.add_argument("--cost", type=float, default=0.5, help="round-trip v bodech (ES: 0.5 = 2 ticky)")
    ap.add_argument("--random-runs", type=int, default=200)
    ap.add_argument("--out", default="reports/es")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rep: list[str] = []
    t0 = _time.time()

    raw = load_csv(args.path, tz=args.data_tz, bar_time=args.bar_time)
    data = resample(raw, args.bar) if args.bar else raw
    loc = data.tz_convert(ET)
    rep += ["# ES: analýza hrany v nejvolatilnějších oknech seance", "",
            f"* Soubor: `{Path(args.path).name}`, surových barů: {len(raw):,}",
            f"* Období: {loc.index[0]} → {loc.index[-1]} ({len(set(loc.index.date)):,} dní)",
            f"* Analyzováno na {args.bar} barech, náklady {args.cost} bodu na round-trip "
            f"(ES tick 0.25 = 12.5 USD)", ""]

    # --- 2. profil volatility
    prof = volatility_profile(data, ET, "30min")
    prof.index = [t.strftime("%H:%M") for t in prof.index]
    prof.index.name = "ET"
    prof.to_csv(out / "volatility_profile.csv")
    rep += ["## 1. Kde je trh nejživější (ET, 30min okna)", "",
            "`rel_range` = průměrný range baru vůči průměru dne (1.0 = průměr).", "",
            md_table(prof.sort_values("rank").head(12)), "",
            md_table(weekday_profile(data, ET)), ""]

    # --- 3.–5. strategie
    base = BacktestConfig(risk=RiskConfig(cost_per_trade=args.cost))
    overview = []
    best_trades = {}
    for label, (preset, only_rth, exit_t, s_grid) in STRATS.items():
        d = rth(data) if only_rth else data
        cfg = replace(base, risk=replace(base.risk, exit_time=exit_t))
        rgrid = MOMENTUM_RISK_GRID if preset == "us_intraday_momentum" else RISK_GRID
        grid = grid_search(d, preset, s_grid, rgrid, cfg)
        grid.to_csv(out / f"grid_{preset}_{label.replace(' ', '_')}.csv", index=False)
        n_trials = len(grid)
        ok = grid[grid["trades"] >= 100]
        if ok.empty:
            rep += [f"## {label}", "", "Méně než 100 obchodů ve všech variantách.", ""]
            continue
        best = ok.sort_values("t_stat", ascending=False).iloc[0]
        s_over = {k: best[k] for k in s_grid}
        r_over = {k[5:]: best[k] for k in rgrid}
        strat = make_strategy(preset, **s_over)
        bcfg = replace(cfg, risk=replace(cfg.risk, **{k: (int(v) if k == "max_trades_per_day" else v)
                                                      for k, v in r_over.items()}))
        v = validate(d, strat, bcfg, n_trials=n_trials, n_random=args.random_runs)
        tr = v["trades"]
        best_trades[label] = (tr, d, strat, bcfg)
        tr.to_csv(out / f"trades_{label.replace(' ', '_')}.csv", index=False)

        # walk-forward přes stejnou mřížku
        wf_grid = [{**a, **b} for a in (param_grid(**s_grid) if s_grid else [{}])
                   for b in param_grid(**rgrid)]
        wf = walk_forward(d, make_strategy(preset), cfg, wf_grid, train_days=750, test_days=250)
        wfs = wf["oos_summary"]

        s = v["summary"]
        overview.append({
            "strategie": label, "obchodů": s["trades"], "win%": s["win_rate"] * 100,
            "E[R]": s["expectancy_r"], "t": s["t_stat"], "PF": s["profit_factor"],
            "rand p": v["random_direction"]["p_value"], "DSR": v["deflated_sharpe"]["dsr"],
            "OOS E[R]": wfs.get("expectancy_r", np.nan), "OOS t": wfs.get("t_stat", np.nan),
            "kontroly": sum(v["checks"].values()),
        })
        rep += [f"## {label}", "",
                f"Nejlepší varianta z {n_trials} pokusů: `{s_over}` + `{r_over}`", "",
                f"* obchodů {s['trades']}, win-rate {s['win_rate']:.1%}, E[R] {s['expectancy_r']:.3f}, "
                f"t {s['t_stat']:.2f}, PF {s['profit_factor']:.2f}, max DD {s['max_drawdown_r']:.1f} R",
                f"* bootstrap 95% CI E[R]: [{v['bootstrap']['ci_low']:.3f}, {v['bootstrap']['ci_high']:.3f}]",
                f"* náhodný směr: p = {v['random_direction']['p_value']:.3f} "
                f"(null průměr {v['random_direction']['null_mean']:.3f})",
                f"* Deflated Sharpe ({n_trials} pokusů): {v['deflated_sharpe']['dsr']:.3f}",
                f"* **Walk-forward OOS**: {wfs.get('trades', 0)} obchodů, "
                f"E[R] {fmt(wfs.get('expectancy_r', np.nan))}, t {fmt(wfs.get('t_stat', np.nan))}",
                f"* Verdikt: **{v['verdict']}**", "",
                "Kontroly: " + ", ".join(f"{'✔' if ok_ else '✘'} {k}" for k, ok_ in v["checks"].items()),
                "", "Po letech:", "", md_table(v["by_year"]), ""]

    ov = pd.DataFrame(overview).set_index("strategie")
    ov.to_csv(out / "overview.csv")

    # --- 6. podmíněné analýzy (kde hrana je / jak ji posunout)
    rep += ["## Podmíněné analýzy", ""]
    for label, (tr, d, strat, bcfg) in best_trades.items():
        if len(tr) < 200:
            continue
        loc_d = d.tz_convert(strat.tz)
        daily = loc_d.groupby(loc_d.index.date).agg(high=("high", "max"), low=("low", "min"))
        prepared = {p.ctx.date: p for p in prepare(d, strat, bcfg)}
        atr = tr["date"].map(lambda x: prepared[x].ctx.atr if x in prepared else np.nan)
        wd = pd.to_datetime(tr["date"]).dt.day_name()
        blocks = [conditional(tr, tr["direction"].map({1: "long", -1: "short"}), "směr"),
                  conditional(tr, wd, "den"),
                  conditional(tr, atr, "ATR kvintil (volatilita režimu)", 5),
                  conditional(tr, tr["risk"] / atr, "riziko/ATR kvintil", 5),
                  conditional(tr, pd.to_datetime(tr["entry_time"]).dt.floor("30min").dt.strftime("%H:%M"),
                              "čas vstupu")]
        rep += [f"### {label}", ""]
        for b in blocks:
            rep += [md_table(b), ""]
        mfe = tr["mfe_r"].quantile([0.25, 0.5, 0.75, 0.9]).round(2).to_dict()
        rep += [f"MFE kvantily (R): {mfe}; MAE medián {tr['mae_r'].median():.2f} R", ""]
        _ = daily

    # intradenní struktura: korelace výnosů 30min oken (odkud pochází momentum/reverze)
    r_rth = rth(data).tz_convert(ET)
    half = r_rth["close"].resample("30min").last().dropna()
    first = r_rth["open"].resample("30min").first().dropna()
    ret = (np.log(half) - np.log(first.reindex(half.index))).dropna()
    tab = ret.to_frame("r")
    tab["date"] = tab.index.date
    tab["slot"] = tab.index.strftime("%H:%M")
    piv = tab.pivot_table(index="date", columns="slot", values="r")
    rth_daily = r_rth.groupby(r_rth.index.date)["close"].last()
    overnight = (np.log(r_rth.groupby(r_rth.index.date)["open"].first()) - np.log(rth_daily.shift(1))).rename("ON")
    piv = piv.join(overnight)
    piv["ON+first30"] = piv["ON"] + piv.get("09:30", 0)
    corr = {c: piv[[c, "15:30"]].dropna().corr().iloc[0, 1] for c in ["ON", "09:30", "ON+first30", "10:00", "15:00"]
            if c in piv}
    rest = piv.drop(columns=["ON", "ON+first30"]).sum(axis=1) - piv["09:30"]
    corr_rest = piv[["09:30"]].join(rest.rename("rest")).dropna().corr().iloc[0, 1]
    rep += ["## Intradenní struktura (RTH)", "",
            "Korelace výnosu poslední půlhodiny (15:30–16:00) s dřívějšími okny "
            "(kladná = momentum, záporná = reverze):", "",
            "\n".join(f"* {k}: {v:+.3f}  (n={piv[[k, '15:30']].dropna().shape[0]})" for k, v in corr.items()),
            f"* první půlhodina vs. zbytek dne: {corr_rest:+.3f}", ""]
    piv.to_csv(out / "rth_30min_returns.csv")

    header = ["## Přehled", "", md_table(ov, 3), "",
              "`rand p` = p-hodnota testu náhodného směru, `DSR` = Deflated Sharpe "
              "(korigováno na počet vyzkoušených variant), `OOS` = walk-forward mimo vzorek "
              "(750 dní trénink / 250 dní test).", ""]
    idx = rep.index("## 1. Kde je trh nejživější (ET, 30min okna)")
    rep = rep[:idx] + header + rep[idx:]
    rep += ["", f"_Výpočet trval {(_time.time() - t0) / 60:.1f} min._"]
    (out / "REPORT.md").write_text("\n".join(rep), encoding="utf-8")
    print("\n".join(rep))


if __name__ == "__main__":
    main()
